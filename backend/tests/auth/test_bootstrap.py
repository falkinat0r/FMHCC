"""Auth-Tests: Bootstrap (R0)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, TEST_BOOTSTRAP_TOKEN


def test_bootstrap_creates_initial_admin(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["username"] == ADMIN_USERNAME
    assert "aendern" in body["message"].lower()


def test_bootstrap_wrong_token_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": "falsches-token-0123456789abcdef"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_bootstrap_without_configured_token(client: TestClient, app) -> None:
    app.state.settings.bootstrap_token = ""
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_configured"


def test_bootstrap_not_available_after_user_exists(client: TestClient) -> None:
    first = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "admin2", "password": "anderes-pass-12345", "token": TEST_BOOTSTRAP_TOKEN},
    )
    assert second.status_code == 403
    assert second.json()["error"]["code"] == "forbidden"


def test_bootstrap_invalid_username(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "A", "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_bootstrap_creates_must_change_password_flag(client: TestClient, db) -> None:
    client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    from sqlalchemy import select

    from app.models.users import User

    user = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert user is not None
    assert user.must_change_password is True
    assert user.role.value == "admin"
