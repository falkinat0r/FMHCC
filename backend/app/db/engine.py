"""Engine-Verwaltung.

Produktion: PostgreSQL (dedizierter User, kein Superuser; nur local/Loopback).
Entwicklung/Test: SQLite erlaubt.
"""

from __future__ import annotations

import threading

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings

_engine_lock = threading.Lock()
_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def get_engine(settings: Settings) -> Engine:
    """Liefert (und cached) die Engine fuer die gegebene Konfiguration."""
    global _engine, _session_factory
    with _engine_lock:
        if _engine is None:
            is_sqlite = settings.database_url.startswith("sqlite")
            _engine = sa_create_engine(
                settings.database_url,
                pool_pre_ping=True,
                connect_args={"check_same_thread": False} if is_sqlite else {},
            )
            _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
        return _engine


def create_engine(settings: Settings) -> Engine:
    """Alias für Tests/Demos mit eigenem, nicht gecachtem Engine-Bau."""
    is_sqlite = settings.database_url.startswith("sqlite")
    return sa_create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )


def get_session_factory() -> sessionmaker:
    assert _session_factory is not None, "Engine wurde noch nicht initialisiert (get_engine aufrufen)"
    return _session_factory


def reset_engine() -> None:
    """Nur fuer Tests: setzt den Cache zurueck."""
    global _engine, _session_factory
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None
