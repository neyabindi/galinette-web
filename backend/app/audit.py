"""
Journal d'audit Galinette — SQLite, local, simple.
Trace qui a fait quoi, quand. C'est ce qui manque à Galinette cendrée originale.
Rétention automatique : 30 jours.
"""
import sqlite3
import time
import threading
from pathlib import Path
from .config import settings

_DB_PATH = Path(settings.data_dir) / "galinette.db"
_LOCK = threading.Lock()
_RETENTION_DAYS = 30


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _LOCK:
        with _conn() as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS audit (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         REAL NOT NULL,
                username   TEXT NOT NULL,
                action     TEXT NOT NULL,
                target     TEXT,
                result     TEXT
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts DESC)")
    # Purge au démarrage
    purge_old()


def purge_old() -> int:
    """Supprime les événements > 30 jours. Retourne le nombre supprimé."""
    cutoff = time.time() - (_RETENTION_DAYS * 86400)
    try:
        with _LOCK:
            with _conn() as c:
                cur = c.execute("DELETE FROM audit WHERE ts < ?", (cutoff,))
                return cur.rowcount
    except Exception:
        return 0


def audit_log(username: str, action: str, target: str, result: str) -> None:
    try:
        with _LOCK:
            with _conn() as c:
                c.execute(
                    "INSERT INTO audit (ts, username, action, target, result) VALUES (?,?,?,?,?)",
                    (time.time(), username, action, target or "", result or ""),
                )
    except Exception:
        # Un échec d'audit ne doit jamais bloquer une action
        pass


def list_audit_events(limit: int = 200, query: str = "") -> list[dict]:
    limit = max(1, min(limit, 1000))
    q = (query or "").strip().lower()
    with _LOCK:
        with _conn() as c:
            if q:
                like = f"%{q}%"
                rows = c.execute(
                    "SELECT ts, username, action, target, result FROM audit "
                    "WHERE LOWER(username) LIKE ? OR LOWER(action) LIKE ? "
                    "   OR LOWER(target) LIKE ? OR LOWER(result) LIKE ? "
                    "ORDER BY ts DESC LIMIT ?",
                    (like, like, like, like, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT ts, username, action, target, result FROM audit "
                    "ORDER BY ts DESC LIMIT ?", (limit,)
                ).fetchall()
            return [
                {
                    "when": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"])),
                    "who": r["username"],
                    "action": r["action"],
                    "target": r["target"],
                    "result": r["result"],
                }
                for r in rows
            ]
