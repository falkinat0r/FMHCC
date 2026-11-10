"""Paging-Tests (frozen Paging-Contract, R0)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.adapters.base import ResourceRecord
from app.inventory.base import upsert_resources
from app.models.integrations import Integration
from app.models.resources import ResourceStatus, ResourceType
from tests.conftest import bootstrap_admin, csrf_headers


def _seed_resources(client: TestClient, db, count: int = 5) -> TestClient:
    """Bootstrapped admin + Integration + Test-VMs (klar als Testdata)."""
    client = bootstrap_admin(client)
    response = client.put(
        "/api/v1/integrations/test-1",
        headers=csrf_headers(client),
        json={"integration_id": "test-1", "name": "Test", "adapter": "proxmox"},
    )
    assert response.status_code == 200, response.text
    # JSON liefert die UUID als String; Uuid(as_uuid=True) erwartet ein
    # uuid.UUID-Objekt fuer das Bind-Parameter.
    integration = db.get(Integration, uuid.UUID(response.json()["id"]))
    base = datetime.now(UTC)
    records = [
        ResourceRecord(
            resource_type=ResourceType.VM,
            external_id=str(100 + i),
            name=f"vm-{i}",
            status=ResourceStatus.HEALTHY if i % 2 == 0 else ResourceStatus.DOWN,
            observed_at=base,
        )
        for i in range(count)
    ]
    upsert_resources(db, integration, records)
    db.commit()
    return client


def test_pagination_counts(client: TestClient, db) -> None:
    client = _seed_resources(client, db, count=5)
    response = client.get("/api/v1/resources", params={"page": 1, "page_size": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert body["page"] == 1
    assert len(body["items"]) == 2


def test_pagination_last_page_partial(client: TestClient, db) -> None:
    client = _seed_resources(client, db, count=5)
    response = client.get("/api/v1/resources", params={"page": 3, "page_size": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1


def test_pagination_page_beyond_range_is_empty(client: TestClient, db) -> None:
    client = _seed_resources(client, db, count=5)
    response = client.get("/api/v1/resources", params={"page": 9, "page_size": 2})
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_resources_filter_by_status_and_type(client: TestClient, db) -> None:
    client = _seed_resources(client, db, count=4)
    response = client.get("/api/v1/resources", params={"status": "down", "resource_type": "vm"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert all(item["status"] == "down" for item in body["items"])


def test_resources_page_size_capped(client: TestClient, db) -> None:
    client = _seed_resources(client, db, count=3)
    response = client.get("/api/v1/resources", params={"page_size": 500})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
