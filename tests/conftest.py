"""QA-Fixtures (Agent 5): API-Integrationstests gegen die R0-App.

Alle Tests laufen gegen in-memory SQLite (ein pro Test, isoliert) und den
FastAPI-TestClient — kein echter Infrastruktur-Zugriff. Die Fixtures
spiegeln die Konventionen aus backend/tests/conftest.py, sind aber
absichtlich selbststaendig, damit der QA-Bereich (tests/) keine
Schreibabhaengigkeit zum Backend-Test-Verzeichnis hat.
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

TEST_BOOTSTRAP_TOKEN = "qa-bootstrap-token-0123456789abcdef"
ADMIN_USERNAME = "qa_admin"
ADMIN_PASSWORD = "qa-admin-pass-1234"
VIEWER_USERNAME = "qa_viewer"
VIEWER_PASSWORD = "qa-viewer-pass-1234"
OPERATOR_USERNAME = "qa_operator"
OPERATOR_PASSWORD = "qa-operator-pass-1234"


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        environment="development",
        database_url="sqlite://",
        bootstrap_token=TEST_BOOTSTRAP_TOKEN,
        cookie_secure=False,
        log_level="WARNING",
        git_commit="qa-test",
    )


@pytest.fixture()
def engine():
    engine_ = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

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
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    auth_routes._login_limiter.reset()
    yield


def login_client(app, username: str, password: str) -> TestClient:
    """Neuer, isolierter TestClient mit einer validen Session fuer den User."""
    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        return test_client


def bootstrap_admin(client: TestClient) -> TestClient:
    """Erzeugt via Bootstrap den Admin und meldet ihn an."""
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    assert response.status_code == 201, response.text
    response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return client


@pytest.fixture()
def admin_client(app) -> TestClient:
    """Eigener, isolierter Client (eigenes Cookie-Jar) — der anonyme
    ``client``-Fixtures bleibt ohne Session."""
    with TestClient(app) as test_client:
        bootstrap_admin(test_client)
        return test_client


def create_user(admin: TestClient, username: str, password: str, role: str) -> dict:
    """Legt ueber die Admin-API einen User an (CSRF Double-Submit)."""
    csrf = admin.cookies.get("hcc_csrf", "")
    response = admin.post(
        "/api/v1/users",
        headers={"X-CSRF-Token": csrf},
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def viewer_client(app, admin_client: TestClient) -> TestClient:
    create_user(admin_client, VIEWER_USERNAME, VIEWER_PASSWORD, "viewer")
    return login_client(app, VIEWER_USERNAME, VIEWER_PASSWORD)


@pytest.fixture()
def operator_client(app, admin_client: TestClient) -> TestClient:
    create_user(admin_client, OPERATOR_USERNAME, OPERATOR_PASSWORD, "operator")
    return login_client(app, OPERATOR_USERNAME, OPERATOR_PASSWORD)
