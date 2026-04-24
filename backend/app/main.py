"""
Galinette Web — API FastAPI
Administration des serveurs RDS (Remote Desktop Services).
"""
from contextlib import asynccontextmanager
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

    task = asyncio.create_task(audit_janitor())
    yield
    task.cancel()
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
async def servers_health(user: SessionUser = Depends(get_current_user)):
    creds = get_current_credentials(user)
    servers = load_servers()
    return {"servers": await list_server_health(servers, creds)}


# ---------- Sessions ----------
@app.get("/api/sessions")
async def list_all_sessions(user: SessionUser = Depends(get_current_user)):
    import asyncio
    creds = get_current_credentials(user)
    servers = load_servers()

    async def one(srv: str):
        try:
            # Timeout 20s par serveur : un RDS lent ne bloque plus toute la requête
            sessions = await asyncio.wait_for(
                list_sessions_on_server(srv, creds),
                timeout=20.0
            )
            return ("ok", srv, sessions)
        except asyncio.TimeoutError:
            return ("err", srv, "délai dépassé (20s)")
        except Exception as e:
            # Message user-friendly au lieu du jargon pypsrp
            msg = str(e)
            if "WSMan" in msg or "5985" in msg:
                msg = "serveur injoignable (WinRM)"
            elif "access denied" in msg.lower() or "accès" in msg.lower():
                msg = "accès refusé"
            elif "Kerberos" in msg:
                msg = "authentification Kerberos échouée"
            return ("err", srv, msg)

    results = await asyncio.gather(*[one(s) for s in servers])
    all_sessions, errors = [], []
    for status, srv, payload in results:
        if status == "ok":
            all_sessions.extend(payload)
        else:
            errors.append({"server": srv, "error": payload})
    return {"sessions": all_sessions, "errors": errors}


@app.post("/api/sessions/{server}/{session_id}/disconnect")
async def api_disconnect(
    server: str, session_id: int, user: SessionUser = Depends(get_current_user)
):
    creds = get_current_credentials(user)
    await disconnect_session(server, session_id, creds)
    audit_log(user.username, "disconnect", f"{server}/#{session_id}", "ok")
    return {"ok": True}


@app.post("/api/sessions/{server}/{session_id}/logoff")
async def api_logoff(
    server: str, session_id: int, user: SessionUser = Depends(get_current_user)
):
    creds = get_current_credentials(user)
    await logoff_session(server, session_id, creds)
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
