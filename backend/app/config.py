"""
Configuration Galinette Web — variables d'environnement et persistance simple.
"""
import os
import json
import threading
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Environnement
    ad_domain: str = "example.local"
    ad_netbios: str = "EXAMPLE"
    ad_dc: str = ""  # rempli automatiquement si vide via DNS SRV
    ad_admin_group: str = "Galinette-Admins"  # groupe requis pour accéder à Galinette

    # Session
    session_ttl_seconds: int = 8 * 3600   # 8h par défaut
    cookie_secure: bool = True            # True en prod (HTTPS via NPM)

    # Audit
    audit_retention_days: int = 90  # rétention du journal d'audit
    database_url: str = ""  # vide = SQLite local. Sinon ex: mysql+pymysql://user:pwd@host:3306/db

    # CORS (dev only, en prod front & back sont derrière NPM)
    cors_origins: list[str] = ["https://galinette.example.local"]

    # Chemins data
    data_dir: str = "/data"

    class Config:
        env_file = ".env"
        env_prefix = "GALINETTE_"


settings = Settings()

_DATA_DIR = Path(settings.data_dir)
try:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
except (PermissionError, OSError):
    import tempfile
    _DATA_DIR = Path(tempfile.gettempdir()) / "galinette"
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

_SERVERS_FILE = _DATA_DIR / "servers.json"
_LOCK = threading.Lock()


def load_servers() -> list[str]:
    """Liste des serveurs RDS à administrer (normalisée en majuscules)."""
    if not _SERVERS_FILE.exists():
        return []
    with _LOCK:
        try:
            raw = json.loads(_SERVERS_FILE.read_text(encoding="utf-8"))
            # Normalise au chargement aussi : protège contre les vieux fichiers avec doublons
            return sorted(set(s.strip().upper() for s in raw if s and s.strip()))
        except Exception:
            return []


def save_servers(servers: list[str]) -> None:
    """Persiste la liste des serveurs (normalisée en majuscules, sans doublons)."""
    # Normalise en majuscules : RDS01 et rds01 deviennent le même serveur
    clean = sorted(set(s.strip().upper() for s in servers if s and s.strip()))
    with _LOCK:
        _SERVERS_FILE.write_text(
            json.dumps(clean, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
