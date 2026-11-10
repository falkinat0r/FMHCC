"""Security-Regression: RBAC-Matrix (serverseitig, pro Endpunkt).

Verbindliches Modell (docs/api-contracts.md §4, R0-frozen):
viewer < operator < admin; Pruefung immer serverseitig pro Endpunkt.

Erwartete Statuscodes:
- 401 unauthenticated: keine Session
- 403 forbidden       : Session, aber Rolle unzureichend
- 200                 : Rolle ausreichend (oder 404/409 bei
  geschaeftsseitig nicht vorhandenem Ziel — nie 401/403)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

USER_ID = "00000000-0000-0000-0000-000000000000"


def _is_auth_or_rbac_rejection(status: int) -> bool:
    return status in (401, 403)


def _code(response) -> str:
    try:
        return response.json().get("error", {}).get("code", "")
    except ValueError:
        return ""


class TestUnauthenticated:
    """Lesende Endpunkte ohne Session => 401 unauthenticated.

    Hinweis: state-aendernde Requests ohne Session werden von der
    CSRF-Middleware abgefangen (403, Matrix in test_csrf_matrix.py),
    weil sie vor der Routen-Authentifizierung laeuft.
    """

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/auth/me",
            "/api/v1/users",
            "/api/v1/integrations",
            "/api/v1/integrations/qa-int",
            "/api/v1/resources",
            "/api/v1/resources/11111111-1111-1111-1111-111111111111",
            "/api/v1/audit",
        ],
    )
    def test_read_requires_session(self, client: TestClient, path: str) -> None:
        response = client.get(path)
        assert response.status_code == 401, f"GET {path}: 401 erwartet, bekam {response.status_code}"
        assert _code(response) == "unauthenticated"

    @pytest.mark.parametrize(
        "method,path",
        [
            ("POST", "/api/v1/auth/logout"),
            ("POST", "/api/v1/users"),
            ("PATCH", f"/api/v1/users/{USER_ID}"),
            ("PUT", "/api/v1/integrations/qa-int"),
            ("POST", "/api/v1/integrations/qa-int/verify"),
            ("DELETE", "/api/v1/integrations/qa-int"),
        ],
    )
    def test_state_change_requires_session_or_csrf(self, client: TestClient, method: str, path: str) -> None:
        response = client.request(method, path, json={} if method in ("POST", "PUT") else None)
        assert response.status_code in (401, 403), (
            f"{method} {path}: Ablehnung erwartet, bekam {response.status_code}"
        )


class TestViewer:
    """viewer: Lesezugriff auf Ressourcen/Integrationen; keine Admin-/
    Schreibrechte; kein Audit."""

    @pytest.mark.parametrize("path", ["/api/v1/integrations", "/api/v1/resources", "/api/v1/auth/me"])
    def test_viewer_reads_allowed(self, viewer_client: TestClient, path: str) -> None:
        assert viewer_client.get(path).status_code == 200

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/v1/users"),
            ("POST", "/api/v1/users"),
            ("PATCH", f"/api/v1/users/{USER_ID}"),
            ("PUT", "/api/v1/integrations/qa-int"),
            ("POST", "/api/v1/integrations/qa-int/verify"),
            ("DELETE", "/api/v1/integrations/qa-int"),
            ("GET", "/api/v1/audit"),
        ],
    )
    def test_viewer_write_and_admin_denied(self, viewer_client: TestClient, method: str, path: str) -> None:
        csrf = viewer_client.cookies.get("hcc_csrf", "")
        response = viewer_client.request(
            method, path, headers={"X-CSRF-Token": csrf}, json={} if method in ("POST", "PUT") else None
        )
        assert response.status_code == 403, f"{method} {path}: 403 erwartet, bekam {response.status_code}"
        assert _code(response) == "forbidden"


class TestOperator:
    """operator: wie viewer + actions.run (R1); in R0 sind Schreib-Endpoints
    fuer Integrationen/User/Audit weiterhin admin-only."""

    @pytest.mark.parametrize("path", ["/api/v1/integrations", "/api/v1/resources", "/api/v1/auth/me"])
    def test_operator_reads_allowed(self, operator_client: TestClient, path: str) -> None:
        assert operator_client.get(path).status_code == 200

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/v1/users"),
            ("POST", "/api/v1/users"),
            ("PUT", "/api/v1/integrations/qa-int"),
            ("POST", "/api/v1/integrations/qa-int/verify"),
            ("DELETE", "/api/v1/integrations/qa-int"),
            ("GET", "/api/v1/audit"),
        ],
    )
    def test_operator_admin_actions_denied(self, operator_client: TestClient, method: str, path: str) -> None:
        csrf = operator_client.cookies.get("hcc_csrf", "")
        response = operator_client.request(
            method, path, headers={"X-CSRF-Token": csrf}, json={} if method in ("POST", "PUT") else None
        )
        assert response.status_code == 403, f"{method} {path}: 403 erwartet, bekam {response.status_code}"
        assert _code(response) == "forbidden"


class TestAdmin:
    """admin: volle Rechte inkl. User-, Integrations- und Audit-Endpunkte."""

    def test_admin_can_list_users(self, admin_client: TestClient) -> None:
        assert admin_client.get("/api/v1/users").status_code == 200

    def test_admin_can_read_audit(self, admin_client: TestClient) -> None:
        response = admin_client.get("/api/v1/audit")
        assert response.status_code == 200

    def test_admin_can_configure_integration(self, admin_client: TestClient) -> None:
        csrf = admin_client.cookies.get("hcc_csrf", "")
        response = admin_client.put(
            "/api/v1/integrations/qa-int",
            headers={"X-CSRF-Token": csrf},
            json={
                "integration_id": "qa-int",
                "name": "QA Integration",
                "adapter": "unknown",
                "base_url": None,
                "secret_ref": None,
            },
        )
        assert response.status_code == 200, response.text

    def test_admin_cannot_demote_last_admin(self, admin_client: TestClient) -> None:
        """Last-Admin-Guard: der einzige aktive Admin darf nicht
        demotiert/deaktiviert werden (409 conflict)."""
        me = admin_client.get("/api/v1/auth/me").json()
        csrf = admin_client.cookies.get("hcc_csrf", "")
        response = admin_client.patch(
            f"/api/v1/users/{me['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"role": "viewer"},
        )
        assert response.status_code == 409, f"Last-Admin-Guard erwartet, bekam {response.status_code}"
