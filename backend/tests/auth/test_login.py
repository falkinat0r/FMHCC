"""Auth-Tests: Login/Logout/Session (R0)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.sessions import SessionService
from app.models.sessions import UserSession
from app.models.users import User
from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, bootstrap_admin, csrf_headers


def test_login_success_sets_cookies(client: TestClient, db) -> None:
    bootstrap_admin(client)
    response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"]
    assert body["session_expires_at"]
    assert "hcc_session" in response.cookies
    assert "hcc_csrf" in response.cookies
    assert client.cookies.get("hcc_session")


def test_login_wrong_password(client: TestClient, db) -> None:
    bootstrap_admin(client)
    response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": "falsches-passwort-1"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert "hcc_session" not in response.cookies


def test_login_unknown_user(client: TestClient, db) -> None:
    bootstrap_admin(client)
    response = client.post("/api/v1/auth/login", json={"username": "niemand", "password": "irgendein-passwort-1"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_login_inactive_user_forbidden(client: TestClient, db) -> None:
    bootstrap_admin(client)
    user = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert user is not None
    user.is_active = False
    db.commit()
    response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_me_requires_session(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_returns_current_user(client: TestClient) -> None:
    client = bootstrap_admin(client)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == ADMIN_USERNAME
    assert body["role"] == "admin"
    assert body["must_change_password"] is True


def test_logout_revokes_session(client: TestClient) -> None:
    client = bootstrap_admin(client)
    assert client.get("/api/v1/auth/me").status_code == 200
    # Logout ist state-aenderung und erfordert den Double-Submit-CSRF-Header
    # (Exemption existiert nur fuer login/bootstrap — siehe app/auth/csrf.py).
    response = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert response.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected(client: TestClient, db, settings) -> None:
    client = bootstrap_admin(client)
    # Eine Session mit abgelaufener Expires-Zeit direkt setzen
    user = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert user is not None
    service = SessionService(settings)
    created = service.create(db, user.id)
    session_row = db.scalar(select(UserSession).where(UserSession.token_hash == service._token_hash(created.raw_token)))
    session_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    response = client.get("/api/v1/auth/me", cookies={"hcc_session": created.raw_token})
    assert response.status_code == 401
