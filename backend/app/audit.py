"""
Journal d'audit Galinette.

Stockage configurable :
- SQLite (par défaut) : fichier local, zéro config
- MariaDB / MySQL : via GALINETTE_DATABASE_URL

Trace qui a fait quoi, quand. Rétention configurable.
"""
import time
import threading
import logging
from pathlib import Path
from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Index
)
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

from .config import settings

log = logging.getLogger("galinette.audit")
_LOCK = threading.Lock()

Base = declarative_base()


class AuditEvent(Base):
    __tablename__ = "audit"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(Float, nullable=False, index=True)
    username = Column(String(255), nullable=False)
    action = Column(String(64), nullable=False)
    target = Column(String(512))
    result = Column(String(64))

    __table_args__ = (
        Index("idx_audit_ts", "ts"),
    )


def _build_db_url() -> str:
    """Construit l'URL SQLAlchemy à partir de la config."""
    if settings.database_url:
        return settings.database_url
    db_file = Path(settings.data_dir) / "galinette.db"
    return f"sqlite:///{db_file}"


_engine = None
_SessionLocal = None


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = _build_db_url()
        backend = url.split("://")[0].split("+")[0]
        log.info("Audit DB backend: %s", backend)
        # Pour MariaDB/MySQL : pool_pre_ping évite les "MySQL has gone away"
        if url.startswith("sqlite"):
            kwargs = {"connect_args": {"check_same_thread": False}}
        else:
            kwargs = {"pool_pre_ping": True, "pool_recycle": 3600}
        _engine = create_engine(url, **kwargs)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def init_db() -> None:
    """Crée la table si nécessaire et purge les vieux événements."""
    eng = _get_engine()
    Base.metadata.create_all(eng)
    purge_old()


def purge_old() -> int:
    """Supprime les événements plus anciens que la rétention configurée."""
    cutoff = time.time() - (settings.audit_retention_days * 86400)
    try:
        with _LOCK:
            with _SessionLocal() as s:
                deleted = s.query(AuditEvent).filter(AuditEvent.ts < cutoff).delete()
                s.commit()
                if deleted:
                    log.info(
                        "Purge audit: %d events older than %d days deleted",
                        deleted, settings.audit_retention_days,
                    )
                return deleted
    except SQLAlchemyError as e:
        log.warning("purge_old failed: %s", e)
        return 0


def audit_log(username: str, action: str, target: str, result: str) -> None:
    """Enregistre un événement d'audit. N'échoue jamais (best effort)."""
    try:
        with _LOCK:
            with _SessionLocal() as s:
                evt = AuditEvent(
                    ts=time.time(),
                    username=username,
                    action=action,
                    target=target or "",
                    result=result or "",
                )
                s.add(evt)
                s.commit()
    except SQLAlchemyError as e:
        log.warning("audit_log failed (event lost): %s", e)


def list_audit_events(limit: int = 200, query: str = "") -> list[dict]:
    """Liste les événements, plus récents en premier. Recherche optionnelle."""
    limit = max(1, min(limit, 1000))
    q = (query or "").strip().lower()
    try:
        with _LOCK:
            with _SessionLocal() as s:
                qry = s.query(AuditEvent)
                if q:
                    like = f"%{q}%"
                    qry = qry.filter(
                        AuditEvent.username.ilike(like) |
                        AuditEvent.action.ilike(like) |
                        AuditEvent.target.ilike(like) |
                        AuditEvent.result.ilike(like)
                    )
                rows = qry.order_by(AuditEvent.ts.desc()).limit(limit).all()
                return [
                    {
                        "when": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.ts)),
                        "who": r.username,
                        "action": r.action,
                        "target": r.target,
                        "result": r.result,
                    }
                    for r in rows
                ]
    except SQLAlchemyError as e:
        log.warning("list_audit_events failed: %s", e)
        return []
