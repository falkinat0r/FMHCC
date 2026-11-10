"""RBAC-Tests: Rollen-Grenzen serverseitig erzwungen (R0)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    VIEWER_PASSWORD,
    VIEWER_USERNAME,
    bootstrap_admin,
    create_viewer,
    csrf_headers,
)


def _viewer_client(client: TestClient) -> TestClient:
    admin = bootstrap_admin(client)
    create_viewer(admin, csrf_headers(admin))
    login = admin.post("/api/v1/auth/login", json={"username": VIEWER_USERNAME, "password": VIEWER_PASSWORD})
    assert login.status_code == 200, login.text
    # Eigenes Jar fuer den Viewer (getrennte Cookies)
    viewer = TestClient(admin.app)
    viewer.post("/api/v1/auth/login", json={"username": VIEWER_USERNAME, "password": VIEWER_PASSWORD})
    return viewer


def test_viewer_can_read_resources(client: TestClient) -> None:
    viewer = _viewer_client(client)
    response = viewer.get("/api/v1/resources")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_viewer_can_read_integrations(client: TestClient) -> None:
    viewer = _viewer_client(client)
    assert viewer.get("/api/v1/integrations").status_code == 200


def test_viewer_cannot_create_users(client: TestClient) -> None:
    viewer = _viewer_client(client)
    response = viewer.post("/api/v1/users", json={"username": "x1", "password": "passwort-12345"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_viewer_cannot_configure_integrations(client: TestClient) -> None:
    viewer = _viewer_client(client)
    response = viewer.put(
        "/api/v1/integrations/proxmox-1",
        json={"integration_id": "proxmox-1", "name": "Proxmox", "adapter": "proxmox"},
    )
    assert response.status_code == 403


def test_viewer_cannot_read_audit(client: TestClient) -> None:
    viewer = _viewer_client(client)
    response = viewer.get("/api/v1/audit")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_admin_can_read_audit(client: TestClient) -> None:
    client = bootstrap_admin(client)
    response = client.get("/api/v1/audit")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    # Bootstrap + Login sind auditiert
    actions = {item["action"] for item in body["items"]}
    assert "auth.bootstrap.success" in actions
    assert "auth.login.success" in actions


def test_unauthenticated_requests_are_rejected(client: TestClient) -> None:
    for path in ("/api/v1/users", "/api/v1/resources", "/api/v1/integrations", "/api/v1/audit"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "unauthenticated", path
