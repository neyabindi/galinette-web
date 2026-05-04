"""
Résolution AD : sAMAccountName -> objectSid

Utilise les credentials de l'admin connecté pour interroger l'AD via LDAP.
Avec un cache TTL pour éviter de spammer le DC.
"""
import time
import logging
import threading
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.protocol.formatters.formatters import format_sid

from .config import settings

log = logging.getLogger("galinette.adsid")

# Cache mémoire : username (lower) -> (sid, ts)
_SID_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 6 * 3600  # 6h
_LOCK = threading.Lock()


def _build_base_dn() -> str:
    return ",".join(f"DC={part}" for part in settings.ad_domain.split("."))


def resolve_sids(usernames: list[str], creds: tuple[str, str]) -> dict[str, str]:
    """
    Résout une liste de sAMAccountName en SIDs via LDAP en UNE seule requête.

    Args:
        usernames: liste de noms (ex: ["jdoe", "ybindika"])
        creds: (DOMAIN\\user, password) — les credentials de l'admin connecté

    Returns:
        dict {username_lower: sid_string}. Les users non trouvés sont absents.
    """
    if not usernames:
        return {}

    # 1) Lookup cache
    now = time.time()
    result: dict[str, str] = {}
    to_query: list[str] = []
    with _LOCK:
        for u in usernames:
            key = u.lower().strip()
            if not key:
                continue
            cached = _SID_CACHE.get(key)
            if cached and (now - cached[1]) < _CACHE_TTL:
                result[key] = cached[0]
            else:
                to_query.append(key)

    if not to_query:
        return result

    # 2) Requête LDAP : un seul filter (|(sAMAccountName=u1)(sAMAccountName=u2)...)
    try:
        username, password = creds
        # Format DOMAIN\sAMAccountName -> on prend le sAMAccountName pour bind UPN
        if "\\" in username:
            sam = username.split("\\", 1)[1]
        else:
            sam = username
        upn = f"{sam}@{settings.ad_domain}"

        # On essaie LDAPS d'abord, fallback LDAP
        servers_to_try = []
        host = settings.ad_dc or settings.ad_domain
        servers_to_try.append(Server(host, port=636, use_ssl=True, get_info=ALL))
        servers_to_try.append(Server(host, port=389, use_ssl=False, get_info=ALL))

        last_err = None
        for server in servers_to_try:
            try:
                conn = Connection(
                    server, user=upn, password=password,
                    authentication="SIMPLE", auto_bind=True, receive_timeout=10,
                )
                base_dn = _build_base_dn()
                # Construit le filtre
                filter_parts = "".join(f"(sAMAccountName={u})" for u in to_query)
                ldap_filter = f"(&(objectClass=user)(|{filter_parts}))"

                conn.search(
                    search_base=base_dn,
                    search_filter=ldap_filter,
                    search_scope=SUBTREE,
                    attributes=["sAMAccountName", "objectSid"],
                    time_limit=10,
                )

                fresh: dict[str, str] = {}
                for entry in conn.entries:
                    sam_attr = str(entry.sAMAccountName.value).lower()
                    sid_raw = entry.objectSid.raw_values[0]  # bytes
                    sid_str = format_sid(sid_raw)
                    fresh[sam_attr] = sid_str
                    result[sam_attr] = sid_str

                # Met à jour le cache
                with _LOCK:
                    for u, sid in fresh.items():
                        _SID_CACHE[u] = (sid, now)

                conn.unbind()
                log.info("Resolved %d/%d SIDs via LDAP", len(fresh), len(to_query))
                return result
            except Exception as e:
                last_err = e
                continue

        log.warning("SID resolution failed: %s", last_err)
        return result
    except Exception as e:
        log.warning("SID resolution exception: %s", e)
        return result


def clear_sid_cache():
    with _LOCK:
        _SID_CACHE.clear()
