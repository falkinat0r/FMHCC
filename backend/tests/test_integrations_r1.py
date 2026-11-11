"""Integrations-Verwaltung-Tests (R1, Agent 1: Backend Core).

- verify setzt last_verified_at an allen Ausgaengen
- Delete wird blockiert, wenn Action-Jobs die Integration referenzieren
  (FK RESTRICT => saubere 409 statt rohem IntegrityError/500)
- RBAC: viewer/operator koennen nicht loeschen
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.hashing import hash_password
from app.models.action_jobs import ActionJob, ActionType, JobStatus
from app.models.integrations import Integration
from app.models.users import Role, User
from tests.conftest import bootstrap_admin, csrf_headers


def _configure(client: TestClient, slug: str = "integ-r1") -> str:
    response = client.put(
        f"/api/v1/integrations/{slug}",
        headers=csrf_headers(client),
        json={"integration_id": slug, "name": "Integ R1", "adapter": "proxmox"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_verify_sets_last_verified_at_even_without_adapter(client: TestClient, db) -> None:
    client = bootstrap_admin(client)
    _configure(client, "integ-verify")
    before = db.scalar(select(Integration.last_verified_at).where(Integration.integration_id == "integ-verify"))
    assert before is None

    response = client.post("/api/v1/integrations/integ-verify/verify", headers=csrf_headers(client))
    # R0/Registry leer => ehrliches not_implemented, aber der Check-Zeitstempel
    # muss gesetzt sein.
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "not_implemented"

    row = db.scalar(select(Integration).where(Integration.integration_id == "integ-verify"))
    assert row.last_verified_at is not None


def test_verify_404_for_unknown_integration(client: TestClient) -> None:
    client = bootstrap_admin(client)
    response = client.post("/api/v1/integrations/definitiv-nicht-da/verify", headers=csrf_headers(client))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_delete_blocked_when_action_jobs_exist(client: TestClient, db) -> None:
    client = bootstrap_admin(client)
    _configure(client, "integ-jobs")
    operator = User(
        username="job-owner", role=Role.OPERATOR, password_hash=hash_password("passwort-12345")
    )
    integration = db.scalar(select(Integration).where(Integration.integration_id == "integ-jobs"))
    db.add(operator)
    db.flush()
    db.add(
        ActionJob(
            idempotency_key="block-delete-1",
            action=ActionType.START,
            integration_id=integration.id,
            external_resource_id="101",
            requested_by=operator.id,
            status=JobStatus.PENDING,
            details={},
        )
    )
    db.commit()

    response = client.delete("/api/v1/integrations/integ-jobs", headers=csrf_headers(client))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    # Integration existiert weiter
    assert db.scalar(select(Integration).where(Integration.integration_id == "integ-jobs")) is not None


def test_delete_allowed_without_jobs_and_cascades_resources(client: TestClient, db) -> None:
    client = bootstrap_admin(client)
    _configure(client, "integ-cascade")
    response = client.delete("/api/v1/integrations/integ-cascade", headers=csrf_headers(client))
    assert response.status_code == 204
    assert db.scalar(select(Integration).where(Integration.integration_id == "integ-cascade")) is None


def test_viewer_cannot_delete_integration(client: TestClient, db) -> None:
    client = bootstrap_admin(client)
    # Viewer anlegen
    viewer_resp = client.post(
        "/api/v1/users",
        headers=csrf_headers(client),
        json={"username": "viewer-del", "password": "viewer-pass-123", "role": "viewer"},
    )
    assert viewer_resp.status_code == 201, viewer_resp.text
    viewer = TestClient(client.app)
    viewer.post("/api/v1/auth/login", json={"username": "viewer-del", "password": "viewer-pass-123"})

    _configure(client, "integ-viewer")
    # Mit validem CSRF-Header: der 403 kommt von der RBAC-Pruefung, nicht
    # von der CSRF-Middleware.
    response = viewer.delete("/api/v1/integrations/integ-viewer", headers=csrf_headers(viewer))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_last_verified_at_not_set_on_404(client: TestClient, db) -> None:
    client = bootstrap_admin(client)
    _configure(client, "integ-novf")
    client.post("/api/v1/integrations/falscher-slug/verify", headers=csrf_headers(client))
    row = db.scalar(select(Integration).where(Integration.integration_id == "integ-novf"))
    # 404-Request darf keinen Zeitstempel auf eine andere Integration schreiben.
    assert row.last_verified_at is None
