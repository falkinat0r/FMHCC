"""CSRF-Tests: Double-Submit-Cookie-Pruefung (R0)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import bootstrap_admin, csrf_headers


def test_state_change_without_csrf_header_is_rejected(client: TestClient) -> None:
    client = bootstrap_admin(client)
    response = client.post("/api/v1/users", json={"username": "x1a", "password": "passwort-12345"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert "CSRF" in response.json()["error"]["message"]


def test_state_change_with_wrong_csrf_header_is_rejected(client: TestClient) -> None:
    client = bootstrap_admin(client)
    response = client.post(
        "/api/v1/users",
        headers={"X-CSRF-Token": "falscher-token-wert-1234567890"},
        json={"username": "x1a", "password": "passwort-12345"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_state_change_with_valid_csrf_succeeds(client: TestClient) -> None:
    client = bootstrap_admin(client)
    response = client.post(
        "/api/v1/users",
        headers=csrf_headers(client),
        json={"username": "x1a", "password": "passwort-12345"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["username"] == "x1a"


def test_read_endpoints_do_not_require_csrf(client: TestClient) -> None:
    client = bootstrap_admin(client)
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/users").status_code == 200


def test_login_is_exempt_from_csrf(client: TestClient) -> None:
    client = bootstrap_admin(client)
    # Login ohne CSRF-Header muss weiterhin funktionieren (Exemption)
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "bootstrap-pass-123"})
    assert response.status_code == 200, response.text


def test_state_change_without_session_is_rejected(client: TestClient) -> None:
    # Kein Session-Cookie, nur CSRF-Header => 403
    response = client.post(
        "/api/v1/users",
        headers={"X-CSRF-Token": "irgendein-wert-123456789012345"},
        json={"username": "x1a", "password": "passwort-12345"},
    )
    assert response.status_code == 403
