"""RBAC-Matrix-Tests (R1): Viewer, Operator, Admin gegen alle Endpunkte.

Ergaenzt die R0-Basis-Tests um die Operator-Rolle (zuvor nur Viewer vs.
Admin) und prueft die serverseitige Pruefung fuer jede Rolle einzeln.
Kein Endpunkt darf durch Rollen-Hoherstufung unerwartete Rechte
verleihen (viewer < operator < admin, zentrale Keys in app/auth/rbac.py).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, TEST_BOOTSTRAP_TOKEN, csrf_headers

OPERATOR_USERNAME = "operator1"
OPERATOR_PASSWORD = "operator-pass-123"


def _bootstrap_once(client: TestClient) -> TestClient:
    """Bootstrap nur einmal pro Test-App; bei vorhandenem Admin nur Login.

    Der Bootstrap-Endpoint ist dauerhaft deaktiviert, sobald ein User
    existiert (403) — daher Toleranz dieses Zustands, sonst 201.
    """
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    assert response.status_code in (201, 403), response.text
    login = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert login.status_code == 200, login.text
    return client


def _create_role_client(client: TestClient, username: str, password: str, role: str) -> TestClient:
    """Erzeugt ueber die Admin-API einen User mit Rolle und liefert sein Client."""
    admin = _bootstrap_once(client)
    response = admin.post(
        "/api/v1/users",
        headers=csrf_headers(admin),
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 201, response.text
    role_client = TestClient(admin.app)
    login = role_client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return role_client


def _matrix(client: TestClient) -> dict[str, TestClient]:
    viewer = _create_role_client(client, "v-matrix", "viewer-pass-123", "viewer")
    operator = _create_role_client(client, OPERATOR_USERNAME, OPERATOR_PASSWORD, "operator")
    admin = _bootstrap_once(client)
    return {"viewer": viewer, "operator": operator, "admin": admin}


def test_read_endpoints_all_authenticated_roles_allowed(client: TestClient) -> None:
    roles = _matrix(client)
    for name, role_client in roles.items():
        assert role_client.get("/api/v1/resources").status_code == 200, name
        assert role_client.get("/api/v1/integrations").status_code == 200, name
        assert role_client.get("/api/v1/auth/me").status_code == 200, name


def test_admin_only_endpoints_denied_for_viewer_and_operator(client: TestClient) -> None:
    roles = _matrix(client)
    for name in ("viewer", "operator"):
        role_client = roles[name]
        assert role_client.get("/api/v1/users").status_code == 403, name
        assert role_client.get("/api/v1/audit").status_code == 403, name
        put = role_client.put(
            "/api/v1/integrations/matrix-1",
            json={"integration_id": "matrix-1", "name": "M", "adapter": "proxmox"},
        )
        assert put.status_code == 403, name
        assert role_client.post("/api/v1/users", json={"username": "m-x", "password": "passwort-12345"}).status_code == 403, name
        assert role_client.delete("/api/v1/integrations/matrix-1").status_code in (403, 404), name
    # Admin darf alle.
    assert roles["admin"].get("/api/v1/users").status_code == 200
    assert roles["admin"].get("/api/v1/audit").status_code == 200
    response = roles["admin"].put(
        "/api/v1/integrations/matrix-1",
        headers=csrf_headers(roles["admin"]),
        json={"integration_id": "matrix-1", "name": "M", "adapter": "proxmox"},
    )
    assert response.status_code == 200, response.text


def test_operator_role_value_is_reported(client: TestClient) -> None:
    operator = _create_role_client(client, OPERATOR_USERNAME, OPERATOR_PASSWORD, "operator")
    body = operator.get("/api/v1/auth/me").json()
    assert body["role"] == "operator"


def test_viewer_cannot_disable_or_change_user_roles(client: TestClient) -> None:
    roles = _matrix(client)
    # Admin legt Operator an; Viewer darf ihn weder patchen noch loeschen.
    admin = roles["admin"]
    created = admin.post(
        "/api/v1/users",
        headers=csrf_headers(admin),
        json={"username": "patch-target", "password": "target-pass-123", "role": "operator"},
    )
    assert created.status_code == 201, created.text
    target_id = created.json()["id"]

    forbidden = roles["viewer"].patch(
        f"/api/v1/users/{target_id}",
        headers=csrf_headers(roles["viewer"]),
        json={"role": "viewer"},
    )
    assert forbidden.status_code == 403
    # Operator darf sich ebenfalls nicht selbst hochstufen.
    self_elevate = roles["operator"].patch(
        f"/api/v1/users/{created.json()['id']}",
        headers=csrf_headers(roles["operator"]),
        json={"role": "admin"},
    )
    assert self_elevate.status_code == 403
    # Admin darf es.
    allowed = admin.patch(f"/api/v1/users/{target_id}", headers=csrf_headers(admin), json={"role": "viewer"})
    assert allowed.status_code == 200, allowed.text


def test_unauthenticated_role_requests_are_rejected_everywhere(client: TestClient) -> None:
    # Matrix aufbauen (nutzt client selbst); fuer die 401-Pruefung ein
    # SEPARATES, unauthentifiziertes Client gegen dieselbe App.
    _matrix(client)
    unauth = TestClient(client.app)
    for path in (
        "/api/v1/users",
        "/api/v1/resources",
        "/api/v1/integrations",
        "/api/v1/audit",
        "/api/v1/auth/me",
    ):
        response = unauth.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "unauthenticated", path
    # State-aendernde Request ohne Session wird bereits von der
    # CSRF-Middleware abgelehnt (403) — vor der RBAC-Pruefung.
    response = unauth.put(
        "/api/v1/integrations/unauth-1",
        json={"integration_id": "unauth-1", "name": "U", "adapter": "docker"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
