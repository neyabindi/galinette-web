"""
Galinette Web — API FastAPI
Administration des serveurs RDS.
"""
from contextlib import asynccontextmanager
import time
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import List, Optional
import logging

from .config import settings, load_servers, save_servers
from .auth import (
    login_user, logout_user, get_current_user,
    get_current_credentials, SessionUser
)
from .rds import (
    list_sessions_on_server, send_message, disconnect_session,
    logoff_session, list_user_processes, unlock_ad_account,
    get_connection_history, list_server_health,
)
from .shadow import build_shadow_rdp
from .audit import audit_log, list_audit_events, purge_old
from .db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("galinette")

# ---------- Cache mémoire (TTL 30 min) ----------
_CACHE: dict[str, dict] = {}
_CACHE_TTL = 30 * 60

def _cache_get(key: str):
    entry = _CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["at"] > _CACHE_TTL:
        del _CACHE[key]
        return None
    return entry

def _cache_set(key: str, data) -> None:
    _CACHE[key] = {"data": data, "at": time.time()}

def _cache_invalidate(key: str) -> None:
    _CACHE.pop(key, None)



@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    init_db()
    log.info("Galinette Web démarrée - %d serveurs configurés", len(load_servers()))

    # Purge audit tous les 24h en tâche de fond
    async def audit_janitor():
        while True:
            await asyncio.sleep(24 * 3600)
            removed = purge_old()
            if removed:
                log.info("Audit purge : %d événements supprimés (> 30 jours)", removed)

    # Refresh sessions + health en arrière-plan toutes les minutes
    async def background_refresher():
        from .auth import get_any_active_credentials, _SESSIONS
        await asyncio.sleep(2)
        log.info("BG refresher started")
        while True:
            try:
                # Log explicite : combien de sessions actives ?
                n_sess = len(_SESSIONS)
                creds = get_any_active_credentials()
                if not creds:
                    log.info("BG refresh: skipped (sessions=%d, creds=None)", n_sess)
                else:
                    log.info("BG refresh: starting (sessions=%d, user=%s)", n_sess, creds[0])
                    servers = load_servers()
                    if servers:
                        try:
                            from .rds import WINRM_BG_SEMAPHORE
                            health = await list_server_health(servers, creds, semaphore=WINRM_BG_SEMAPHORE)
                            ok = sum(1 for h in health if h.get("reachable"))
                            # Ne pas écraser un bon cache avec un cache vide
                            if ok > 0 or not _CACHE.get("health"):
                                _cache_set("health", health)
                                log.info("BG refresh health OK (%d/%d en ligne)", ok, len(servers))
                            else:
                                log.warning(
                                    "BG refresh health: 0/%d en ligne (cache préservé)",
                                    len(servers),
                                )
                        except Exception as e:
                            log.warning("BG refresh health failed: %s", e)

                        try:
                            from .rds import _run_ps, PS_LIST_SESSIONS, WINRM_BG_SEMAPHORE

                            async def fetch_one(srv):
                                # Sémaphore BG dédié : ne bloque pas les actions admin
                                async with WINRM_BG_SEMAPHORE:
                                    try:
                                        result = await asyncio.wait_for(
                                            asyncio.to_thread(_run_ps, srv, PS_LIST_SESSIONS, creds),
                                            timeout=60.0,
                                        )
                                        return ("ok", srv, result)
                                    except asyncio.TimeoutError:
                                        return ("err", srv, "timeout")
                                    except Exception as e:
                                        return ("err", srv, f"{type(e).__name__}: {e}")

                            results = await asyncio.gather(*[fetch_one(s) for s in servers])
                            all_sessions, errors = [], []
                            for status, srv, payload in results:
                                if status == "ok":
                                    # Applique la normalisation state/idle (comme list_sessions_on_server)
                                    for sess in payload:
                                        st = (sess.get("state") or "").lower().strip()
                                        if st in ("active", "actif"):
                                            sess["state"] = "active"
                                        elif "disc" in st or "déco" in st or "deco" in st:
                                            sess["state"] = "disconnected"
                                        elif "idle" in st or "inact" in st:
                                            sess["state"] = "idle"
                                        else:
                                            sess["state"] = "disconnected"
                                        idle = (sess.get("idle_time") or "").strip()
                                        if idle in (".", "", "0"):
                                            sess["idle_time"] = "-"
                                        elif idle.isdigit():
                                            sess["idle_time"] = f"{idle} min"
                                    all_sessions.extend(payload)
                                else:
                                    errors.append({"server": srv, "error": payload})
                                    log.warning("BG sessions %s: %s", srv, payload)

                            # Enrichit les sessions avec leurs SIDs (via LDAP, en une requête)
                            try:
                                from .adsid import resolve_sids
                                usernames = list({s.get("user", "") for s in all_sessions if s.get("user")})
                                sid_map = await asyncio.to_thread(resolve_sids, usernames, creds)
                                for s in all_sessions:
                                    s["user_sid"] = sid_map.get((s.get("user") or "").lower(), "")
                            except Exception as e:
                                log.warning("SID enrichment failed: %s", e)
                                for s in all_sessions:
                                    s["user_sid"] = ""
                            if all_sessions or not errors or not _CACHE.get("sessions"):
                                _cache_set("sessions", {"sessions": all_sessions, "errors": errors})
                                log.info("BG refresh sessions OK (%d sessions, %d errors)",
                                         len(all_sessions), len(errors))
                            else:
                                log.warning(
                                    "BG refresh sessions: %d errors / %d serveurs (cache préservé)",
                                    len(errors), len(servers),
                                )
                        except Exception as e:
                            log.warning("BG refresh sessions failed: %s", e, exc_info=True)
            except Exception as e:
                log.warning("BG refresher iteration error: %s", e, exc_info=True)
            await asyncio.sleep(60)

    task1 = asyncio.create_task(audit_janitor())
    task2 = asyncio.create_task(background_refresher())
    yield
    task1.cancel()
    task2.cancel()
    log.info("Galinette Web arrêtée")


app = FastAPI(
    title="Galinette Web",
    version="1.0.0",
    description="Modern web-based RDS administration console",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Schémas Pydantic ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class MessageRequest(BaseModel):
    title: str = "Information administrateur"
    body: str


class ServerPayload(BaseModel):
    name: str


# ---------- Auth ----------
@app.post("/api/auth/login")
async def login(req: LoginRequest, response: Response):
    token = await login_user(req.username, req.password)
    response.set_cookie(
        key="galinette_token",
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    audit_log(req.username, "login", "self", "ok")
    return {"username": req.username, "ok": True}


@app.post("/api/auth/logout")
async def logout(response: Response, user: SessionUser = Depends(get_current_user)):
    logout_user(user.token)
    response.delete_cookie("galinette_token")
    audit_log(user.username, "logout", "self", "ok")
    return {"ok": True}


@app.get("/api/auth/me")
async def me(user: SessionUser = Depends(get_current_user)):
    return {"username": user.username, "domain": settings.ad_domain}


# ---------- Serveurs ----------
@app.get("/api/servers")
async def list_servers(user: SessionUser = Depends(get_current_user)):
    return {"servers": load_servers()}


@app.post("/api/servers")
async def add_server(
    payload: ServerPayload, user: SessionUser = Depends(get_current_user)
):
    servers = load_servers()
    if payload.name in servers:
        raise HTTPException(409, "Serveur déjà présent")
    servers.append(payload.name)
    save_servers(servers)
    audit_log(user.username, "server-add", payload.name, "ok")
    return {"servers": servers}


@app.delete("/api/servers/{name}")
async def remove_server(name: str, user: SessionUser = Depends(get_current_user)):
    servers = load_servers()
    if name not in servers:
        raise HTTPException(404, "Serveur inconnu")
    servers = [s for s in servers if s != name]
    save_servers(servers)
    audit_log(user.username, "server-remove", name, "ok")
    return {"servers": servers}


@app.get("/api/servers/health")
async def servers_health(
    user: SessionUser = Depends(get_current_user),
    refresh: bool = False,
):
    """Sert toujours le cache (alimenté par la tâche de fond toutes les 2 min).
    refresh=true déclenche un refresh immédiat en arrière-plan, mais on retourne le cache courant."""
    import asyncio
    if refresh:
        # Déclenche un refresh hors-bande, ne bloque pas la réponse
        asyncio.create_task(_force_refresh("health", user))
    cached = _cache_get("health") or _CACHE.get("health")
    if cached:
        return {"servers": cached["data"], "cached_at": cached["at"], "from_cache": True}
    return {"servers": [], "cached_at": 0, "from_cache": True, "warming": True}


# ---------- Sessions ----------
@app.get("/api/sessions")
async def list_all_sessions(
    user: SessionUser = Depends(get_current_user),
    refresh: bool = False,
):
    """Sert toujours le cache (alimenté par la tâche de fond toutes les 2 min)."""
    import asyncio
    if refresh:
        asyncio.create_task(_force_refresh("sessions", user))
    cached = _cache_get("sessions") or _CACHE.get("sessions")
    if cached:
        return {**cached["data"], "cached_at": cached["at"], "from_cache": True}
    return {"sessions": [], "errors": [], "cached_at": 0, "from_cache": True, "warming": True}


async def _force_refresh(kind: str, user: SessionUser):
    """Lance un refresh manuel en tâche de fond (déclenché par le bouton ↻).
    Utilise la même logique que la tâche BG pour rester cohérent."""
    import asyncio
    try:
        creds = get_current_credentials(user)
        servers = load_servers()
        if not servers:
            return
        if kind == "health":
            data = await list_server_health(servers, creds)
            ok = sum(1 for h in data if h.get("reachable"))
            if ok > 0 or not _CACHE.get("health"):
                _cache_set("health", data)
                log.info("Manual refresh health OK (%d/%d en ligne)", ok, len(servers))
            else:
                log.warning("Manual refresh health: 0 en ligne (cache préservé)")
        elif kind == "sessions":
            from .rds import _run_ps, PS_LIST_SESSIONS, WINRM_SEMAPHORE

            async def fetch_one(srv):
                async with WINRM_SEMAPHORE:
                    try:
                        result = await asyncio.wait_for(
                            asyncio.to_thread(_run_ps, srv, PS_LIST_SESSIONS, creds),
                            timeout=60.0,
                        )
                        return ("ok", srv, result)
                    except asyncio.TimeoutError:
                        return ("err", srv, "timeout")
                    except Exception as e:
                        return ("err", srv, f"{type(e).__name__}: {e}")

            results = await asyncio.gather(*[fetch_one(s) for s in servers])
            all_sessions, errors = [], []
            for status, srv, payload in results:
                if status == "ok":
                    for sess in payload:
                        st = (sess.get("state") or "").lower().strip()
                        if st in ("active", "actif"):
                            sess["state"] = "active"
                        elif "disc" in st or "déco" in st or "deco" in st:
                            sess["state"] = "disconnected"
                        elif "idle" in st or "inact" in st:
                            sess["state"] = "idle"
                        else:
                            sess["state"] = "disconnected"
                        idle = (sess.get("idle_time") or "").strip()
                        if idle in (".", "", "0"):
                            sess["idle_time"] = "-"
                        elif idle.isdigit():
                            sess["idle_time"] = f"{idle} min"
                    all_sessions.extend(payload)
                else:
                    errors.append({"server": srv, "error": payload})

            # Enrichit avec les SIDs LDAP
            try:
                from .adsid import resolve_sids
                usernames = list({s.get("user", "") for s in all_sessions if s.get("user")})
                sid_map = await asyncio.to_thread(resolve_sids, usernames, creds)
                for s in all_sessions:
                    s["user_sid"] = sid_map.get((s.get("user") or "").lower(), "")
            except Exception as e:
                log.warning("Manual SID enrichment failed: %s", e)
                for s in all_sessions:
                    s["user_sid"] = ""

            # Ne pas écraser un bon cache avec un cache vide
            if all_sessions or not errors or not _CACHE.get("sessions"):
                _cache_set("sessions", {"sessions": all_sessions, "errors": errors})
                log.info("Manual refresh sessions OK (%d sessions, %d errors)",
                         len(all_sessions), len(errors))
            else:
                log.warning(
                    "Manual refresh sessions: %d errors / %d serveurs (cache préservé)",
                    len(errors), len(servers),
                )
    except Exception as e:
        log.warning("Manual refresh %s failed: %s", kind, e)


@app.post("/api/sessions/{server}/{session_id}/disconnect")
async def api_disconnect(
    server: str, session_id: int, user: SessionUser = Depends(get_current_user)
):
    creds = get_current_credentials(user)
    await disconnect_session(server, session_id, creds)
    _cache_invalidate("sessions")
    audit_log(user.username, "disconnect", f"{server}/#{session_id}", "ok")
    return {"ok": True}


@app.post("/api/sessions/{server}/{session_id}/logoff")
async def api_logoff(
    server: str, session_id: int, user: SessionUser = Depends(get_current_user)
):
    creds = get_current_credentials(user)
    await logoff_session(server, session_id, creds)
    _cache_invalidate("sessions")
    audit_log(user.username, "logoff", f"{server}/#{session_id}", "ok")
    return {"ok": True}


@app.post("/api/sessions/{server}/{session_id}/message")
async def api_message(
    server: str,
    session_id: int,
    payload: MessageRequest,
    user: SessionUser = Depends(get_current_user),
):
    creds = get_current_credentials(user)
    await send_message(server, session_id, payload.title, payload.body, creds)
    audit_log(user.username, "message", f"{server}/#{session_id}", "ok")
    return {"ok": True}


@app.get("/api/sessions/{server}/{session_id}/processes")
async def api_processes(
    server: str, session_id: int, user: SessionUser = Depends(get_current_user)
):
    creds = get_current_credentials(user)
    procs = await list_user_processes(server, session_id, creds)
    return {"processes": procs}


# ---------- Shadow ----------
@app.get("/api/sessions/{server}/{session_id}/shadow")
async def api_shadow(
    server: str,
    session_id: int,
    mode: str = "force-control",
    user: SessionUser = Depends(get_current_user),
):
    """
    Génère un fichier .bat qui lance mstsc en mode shadow.
    mode : view | control | force-view | force-control
    """
    if mode not in ("view", "control", "force-view", "force-control"):
        raise HTTPException(400, "Mode invalide")
    bat_content = build_shadow_rdp(server, session_id, mode)
    filename = f"shadow_{server}_{session_id}.bat"
    audit_log(user.username, f"shadow-{mode}", f"{server}/#{session_id}", "ok")
    return PlainTextResponse(
        content=bat_content,
        media_type="application/bat",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- Utilisateurs AD ----------
@app.post("/api/users/{sam}/unlock")
async def api_unlock(sam: str, user: SessionUser = Depends(get_current_user)):
    creds = get_current_credentials(user)
    await unlock_ad_account(sam, creds)
    audit_log(user.username, "ad-unlock", sam, "ok")
    return {"ok": True}


@app.get("/api/users/{sam}/history")
async def api_history(sam: str, user: SessionUser = Depends(get_current_user)):
    creds = get_current_credentials(user)
    history = await get_connection_history(sam, creds, load_servers())
    return {"history": history}


# ---------- Audit ----------
@app.get("/api/audit")
async def api_audit(
    limit: int = 500,
    q: str = "",
    user: SessionUser = Depends(get_current_user),
):
    return {"events": list_audit_events(limit, q)}


# ---------- Santé ----------
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": app.version}
