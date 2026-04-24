"""Initialisation de la base SQLite (audit + future config si besoin)."""
from .audit import init_db as _init_audit


def init_db() -> None:
    _init_audit()
