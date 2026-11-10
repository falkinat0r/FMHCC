"""Gemeinsame Test-Fixtures (Foundation, R0).

Konvention:
- Alle Tests laufen gegen in-memory SQLite (ein pro Test, isoliert).
- Kein echter Infrastruktur-Zugriff, keine Secrets (nur Test-Placeholder).
- Rate-Limiter wird pro Test zurueckgesetzt.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import auth as auth_routes
from app.config import Settings
from app.db.base import Base
from app.main import create_app

TEST_BOOTSTRAP_TOKEN = "test-bootstrap-token-0123456789abcdef"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "bootstrap-pass-123"
VIEWER_USERNAME = "viewer1"
VIEWER_PASSWORD = "viewer-pass-123"


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        environment="development",
        database_url="sqlite://",
        bootstrap_token=TEST_BOOTSTRAP_TOKEN,
        cookie_secure=False,
        log_level="WARNING",
        git_commit="test",
    )


@pytest.fixture()
def engine():
    engine_ = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite enforcing FKs is opt-in — Tests muessen Produktionssemantik haben.
    @event.listens_for(engine_, "connect")
    def _enable_sqlite_fks(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine_)
    yield engine_
    engine_.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest.fixture()
def app(settings, session_factory):
    application = create_app(settings)
    application.state.session_factory = session_factory
    return application


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # Alle modularen Rate-Limiter zuruecksetzen, damit Limits nicht
    # zwischen Tests leaken (R1: zusatzlich Bootstrap-Limiter).
    auth_routes._login_limiter.reset()
    if hasattr(auth_routes, "_bootstrap_limiter"):
        auth_routes._bootstrap_limiter.reset()
    yield


def csrf_headers(client: TestClient, csrf_cookie_name: str = "hcc_csrf") -> dict[str, str]:
    """Liest das CSRF-Cookie aus dem Jar und liefert den noetigen Header."""
    token = client.cookies.get(csrf_cookie_name, "")
    return {"X-CSRF-Token": token} if token else {}


def bootstrap_admin(client: TestClient) -> TestClient:
    """Erzeugt via Bootstrap den Admin und meldet ihn an (Cookies im Jar).

    Regulaere Hilfsfunktion (kein Fixture) — darf direkt aufgerufen werden.
    """
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    assert response.status_code == 201, response.text
    response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return client


@pytest.fixture()
def admin_client(client: TestClient) -> TestClient:
    return bootstrap_admin(client)


def create_viewer(client: TestClient, csrf: dict[str, str]) -> None:
    """Erzeugt ueber die Admin-API einen Viewer (braucht CSRF-Header)."""
    response = client.post(
        "/api/v1/users",
        headers=csrf,
        json={"username": VIEWER_USERNAME, "password": VIEWER_PASSWORD, "role": "viewer"},
    )
    assert response.status_code == 201, response.text
