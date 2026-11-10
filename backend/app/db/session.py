"""Session-Handling und FastAPI-Dependency.

Die Session-Factory wird von ``app.main`` aus den Settings erzeugt und auf
``app.state.session_factory`` gelegt. Tests ersetzen ``get_db`` ueber
``app.dependency_overrides`` — keine globalen Engine-Caches.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db(request: Request) -> Generator[Session, None, None]:
    """FastAPI-Dependency: Session pro Request; Commit am Ende, Rollback bei Fehler."""
    factory = request.app.state.session_factory
    db: Session = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
