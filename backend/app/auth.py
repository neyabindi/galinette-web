"""
Authentification Galinette Web

- Login : bind LDAP avec les identifiants de l'admin
- Les credentials sont chiffrés en mémoire (Fernet) et jamais persistés sur disque
- Un cookie HttpOnly contient juste un token de session opaque
- Les actions RDS utilisent les credentials de l'admin connecté (impersonation)
"""
import os
import secrets
import time
import threading
import logging
from dataclasses import dataclass
from fastapi import Cookie, HTTPException, Depends
from cryptography.fernet import Fernet
from ldap3 import Server, Connection, ALL, SIMPLE, Tls
from ldap3.core.exceptions import LDAPException
import ssl

from .config import settings

log = logging.getLogger("galinette.auth")


# Clé de chiffrement générée au démarrage — les credentials en mémoire
# ne sont pas lisibles via un dump mémoire simple
_ENCRYPTION_KEY = Fernet.generate_key()
_FERNET = Fernet(_ENCRYPTION_KEY)

# Store des sessions en mémoire : token -> SessionData
_SESSIONS: dict[str, "SessionData"] = {}
_LOCK = threading.Lock()


@dataclass
class SessionData:
    username: str               # sAMAccountName (e.g. john.doe)
    domain: str                 # NetBIOS domain name
    enc_password: bytes         # mot de passe chiffré Fernet
    created_at: float
    last_seen: float


@dataclass
class SessionUser:
    token: str
    username: str
    domain: str


def _try_bind(host: str, port: int, use_ssl: bool, bind_user: str, password: str) -> tuple[bool, str]:
    """Tente un bind LDAP SIMPLE (UPN), retourne (success, diagnostic)."""
    try:
        if use_ssl:
            tls = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
            server = Server(host, port=port, use_ssl=True, tls=tls, get_info=ALL, connect_timeout=5)
        else:
            server = Server(host, port=port, get_info=ALL, connect_timeout=5)

        conn = Connection(
            server,
            user=bind_user,
            password=password,
            authentication=SIMPLE,
            auto_bind=True,
            read_only=True,
            receive_timeout=10,
        )
        conn.unbind()
        return True, "ok"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _ldap_authenticate(username: str, password: str) -> bool:
    """
    Teste l'auth LDAP via SIMPLE bind UPN.
    Essaie LDAPS puis LDAP clair.
    """
    host = settings.ad_dc or settings.ad_domain
    # Format UPN : user@domain.tld (recommandé par Microsoft pour SIMPLE bind)
    upn = f"{username}@{settings.ad_domain}"
    log.info("LDAP auth attempt: user=%s host=%s", upn, host)

    # Essai LDAPS
    ok, diag = _try_bind(host, 636, True, upn, password)
    log.info("LDAPS 636 result: ok=%s diag=%s", ok, diag)
    if ok:
        return True

    # Essai LDAP clair
    ok, diag = _try_bind(host, 389, False, upn, password)
    log.info("LDAP 389 result: ok=%s diag=%s", ok, diag)
    return ok


def _is_in_admin_group(username: str, password: str) -> tuple[bool, str]:
    """
    Vérifie que le user est membre (direct ou imbriqué) du groupe ad_admin_group.
    Retourne (True, "") si membre, (False, "raison") sinon.
    """
    host = settings.ad_dc or settings.ad_domain
    upn = f"{username}@{settings.ad_domain}"
    group = settings.ad_admin_group

    # Construit la base DN à partir du domaine (example.local -> DC=example,DC=local)
    base_dn = ",".join(f"DC={p}" for p in settings.ad_domain.split("."))

    # Essaie LDAPS puis LDAP clair
    for port, use_ssl in [(636, True), (389, False)]:
        try:
            if use_ssl:
                tls = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
                server = Server(host, port=port, use_ssl=True, tls=tls,
                                get_info=ALL, connect_timeout=5)
            else:
                server = Server(host, port=port, get_info=ALL, connect_timeout=5)

            conn = Connection(
                server, user=upn, password=password,
                authentication=SIMPLE, auto_bind=True, read_only=True,
                receive_timeout=10,
            )

            # Recherche du DN du groupe
            conn.search(
                search_base=base_dn,
                search_filter=f"(&(objectClass=group)(sAMAccountName={group}))",
                attributes=["distinguishedName"],
            )
            if not conn.entries:
                conn.unbind()
                return False, f"Groupe '{group}' introuvable dans l'AD"

            group_dn = conn.entries[0].distinguishedName.value

            # Recherche du user avec filtre memberOf récursif (LDAP_MATCHING_RULE_IN_CHAIN)
            # 1.2.840.113556.1.4.1941 résout aussi les groupes imbriqués
            user_filter = (
                f"(&(sAMAccountName={username})"
                f"(memberOf:1.2.840.113556.1.4.1941:={group_dn}))"
            )
            conn.search(
                search_base=base_dn,
                search_filter=user_filter,
                attributes=["sAMAccountName"],
            )
            is_member = len(conn.entries) > 0
            conn.unbind()

            if is_member:
                return True, ""
            return False, f"Non membre du groupe {group}"
        except Exception as e:
            log.info("Group check via port %d failed: %s", port, e)
            continue

    return False, "Impossible de vérifier l'appartenance au groupe"


async def login_user(username: str, password: str) -> str:
    """
    Authentifie l'utilisateur contre l'AD et renvoie un token de session.
    Refuse l'accès si le user n'est pas membre du groupe configuré.
    """
    if not username or not password:
        raise HTTPException(400, "Identifiants manquants")

    # Strip éventuel préfixe domaine
    clean_user = username.replace(f"{settings.ad_netbios}\\", "").replace(
        f"{settings.ad_domain}\\", ""
    )

    if not _ldap_authenticate(clean_user, password):
        raise HTTPException(401, "Échec d'authentification Active Directory")

    # Vérifie l'appartenance au groupe admin
    ok, reason = _is_in_admin_group(clean_user, password)
    log.info("Group membership check for %s: ok=%s reason=%s", clean_user, ok, reason)
    if not ok:
        raise HTTPException(
            403,
            "Accès refusé : vous n'êtes pas administrateur. "
            "Merci de réessayer avec un compte admin autorisé.",
        )

    # Crée un token de session opaque
    token = secrets.token_urlsafe(32)
    now = time.time()

    with _LOCK:
        _SESSIONS[token] = SessionData(
            username=clean_user,
            domain=settings.ad_netbios,
            enc_password=_FERNET.encrypt(password.encode("utf-8")),
            created_at=now,
            last_seen=now,
        )

    _purge_expired_sessions()
    return token


def logout_user(token: str) -> None:
    with _LOCK:
        _SESSIONS.pop(token, None)


def _purge_expired_sessions() -> None:
    now = time.time()
    ttl = settings.session_ttl_seconds
    with _LOCK:
        expired = [t for t, s in _SESSIONS.items() if now - s.last_seen > ttl]
        for t in expired:
            _SESSIONS.pop(t, None)


def get_current_user(
    galinette_token: str | None = Cookie(default=None)
) -> SessionUser:
    """Dependency FastAPI : récupère l'user depuis le cookie."""
    if not galinette_token:
        raise HTTPException(401, "Non authentifié")

    with _LOCK:
        sess = _SESSIONS.get(galinette_token)
        if not sess:
            raise HTTPException(401, "Session expirée ou inconnue")
        if time.time() - sess.last_seen > settings.session_ttl_seconds:
            _SESSIONS.pop(galinette_token, None)
            raise HTTPException(401, "Session expirée")
        sess.last_seen = time.time()

    return SessionUser(
        token=galinette_token,
        username=sess.username,
        domain=sess.domain,
    )


def get_current_credentials(user: SessionUser) -> tuple[str, str]:
    """
    Retourne (username_domaine, password_clair) pour pypsrp.
    Jamais loggé, jamais persisté.
    """
    with _LOCK:
        sess = _SESSIONS.get(user.token)
        if not sess:
            raise HTTPException(401, "Session invalide")
        password = _FERNET.decrypt(sess.enc_password).decode("utf-8")

    # Format attendu par pypsrp en auth NTLM
    return f"{settings.ad_netbios}\\{sess.username}", password
