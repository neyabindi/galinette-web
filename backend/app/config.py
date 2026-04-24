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
    cookie_secure: bool = True            # True en prod (HTTPS via reverse proxy)

    # CORS (dev only, en prod front & back sont derrière un reverse proxy)
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8082"]

    # Chemins data
    data_dir: str = "/data"

    class Config:
        env_file = ".env"
        env_prefix = "GALINETTE_"


settings = Settings()

_DATA_DIR = Path(settings.data_dir)
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_SERVERS_FILE = _DATA_DIR / "servers.json"
_LOCK = threading.Lock()


def load_servers() -> list[str]:
    """Liste des serveurs RDS à administrer."""
    if not _SERVERS_FILE.exists():
        return []
    with _LOCK:
        try:
            return json.loads(_SERVERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []


def save_servers(servers: list[str]) -> None:
    """Persiste la liste des serveurs."""
    clean = sorted(set(s.strip() for s in servers if s and s.strip()))
    with _LOCK:
        _SERVERS_FILE.write_text(
            json.dumps(clean, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
