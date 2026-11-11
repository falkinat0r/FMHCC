"""Adapter-Interface-Tests (frozen Protokoll, R0).

Ein FakeAdapter beweist die Testbarkeit des Protokolls: Registry,
Verify-Flow, Fehlermauerung, SecretsProvider, Act-Schutz.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.adapters.base import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterState,
    AdapterStatus,
    BaseAdapter,
    ResourceRecord,
)
from app.adapters.errors import AdapterAuthError, AdapterError
from app.adapters.secrets import EnvSecretsProvider, InvalidSecretRefError
from app.integrations import registry
from app.models.integrations import AdapterKind, IntegrationStatus
from app.models.resources import ResourceStatus, ResourceType
from tests.conftest import bootstrap_admin, csrf_headers


class FakeAdapter(BaseAdapter):
    """Bewusster Test-Adapter (klar als Test-Datum gekennzeichnet)."""

    kind = AdapterKind.PROXMOX

    async def verify(self, config: AdapterConfig, secrets) -> AdapterStatus:
        if config.secret_ref is None or secrets.get(config.secret_ref) is None:
            raise AdapterAuthError("API-Token nicht konfiguriert")
        return AdapterStatus(state=AdapterState.OK, api_version="8.2", checked_at=datetime.now(UTC))

    async def capabilities(self, config: AdapterConfig, secrets) -> AdapterCapabilities:
        return AdapterCapabilities(features=["discover", "health", "metrics"], api_version="8.2")

    async def discover(self, config: AdapterConfig, secrets):
        yield ResourceRecord(
            resource_type=ResourceType.HOST,
            external_id="node1",
            name="node1",
            status=ResourceStatus.HEALTHY,
            observed_at=datetime.now(UTC),
        )
        yield ResourceRecord(
            resource_type=ResourceType.VM,
            external_id="101",
            name="atlas-fixture",
            status=ResourceStatus.UNKNOWN,
            observed_at=datetime.now(UTC),
            parent_external_id="node1",
            parent_resource_type=ResourceType.HOST,
        )


@pytest.fixture(autouse=True)
def _register_fake_adapter():
    # R1-Integration: create_app() befuellt die Registry inzwischen
    # (register_all_adapters); die Fixture startet daher — wie
    # tests/proxmox/conftest.py — immer von einer leeren Registry.
    registry._reset_for_tests()
    registry.register(FakeAdapter)
    yield
    registry._reset_for_tests()


def test_registry_lookup() -> None:
    assert registry.get_adapter(AdapterKind.PROXMOX) is FakeAdapter
    assert "proxmox" in registry.available_adapters()
    assert registry.get_adapter("kein-adapter") is None


def test_fake_adapter_implements_protocol() -> None:
    config = AdapterConfig(secret_ref="FAKE_TOKEN")
    secrets = EnvSecretsProvider({"FAKE_TOKEN": "test-wert"})
    status = asyncio.run(FakeAdapter().verify(config, secrets))
    assert status.state is AdapterState.OK

    # discover() ist ein Async-Generator — muss per async for entleert werden
    async def drain() -> list[ResourceRecord]:
        return [record async for record in FakeAdapter().discover(config, secrets)]

    records = asyncio.run(drain())
    assert [r.external_id for r in records] == ["node1", "101"]


def test_act_requires_confirmation() -> None:
    adapter = FakeAdapter()
    config = AdapterConfig()
    secrets = EnvSecretsProvider({})
    with pytest.raises(AdapterError) as exc_info:
        asyncio.run(adapter.act(config, secrets, "start", "101", confirmed=False))
    assert exc_info.value.state is AdapterState.NOT_CONFIGURED
    with pytest.raises(AdapterError) as exc_info2:
        asyncio.run(adapter.act(config, secrets, "start", "101", confirmed=True))
    assert exc_info2.value.state is AdapterState.NOT_IMPLEMENTED


def test_collect_default_not_implemented() -> None:
    adapter = FakeAdapter()
    with pytest.raises(AdapterError) as exc_info:
        asyncio.run(adapter.collect(AdapterConfig(), EnvSecretsProvider({}), ResourceType.VM, "101"))
    assert exc_info.value.state is AdapterState.NOT_IMPLEMENTED


def test_secrets_provider_validates_names() -> None:
    provider = EnvSecretsProvider({"FAKE_TOKEN": "wert", "OTHER": "x"})
    assert provider.get("FAKE_TOKEN") == "wert"
    assert provider.get("UNKNOWN_REF") is None
    with pytest.raises(InvalidSecretRefError):
        provider.get("../etc/passwd")
    with pytest.raises(InvalidSecretRefError):
        provider.get("123-begint-nicht-mit-buchstabe")


def test_verify_endpoint_success(client: TestClient) -> None:
    client = bootstrap_admin(client)
    client.put(
        "/api/v1/integrations/proxmox-1",
        headers=csrf_headers(client),
        json={
            "integration_id": "proxmox-1",
            "name": "Proxmox (Test-Fixture)",
            "adapter": "proxmox",
            "base_url": "https://pve.example.lan:8006",
            "secret_ref": "PROXMOX_API_TOKEN",
        },
    )
    # Secret muss in der Umgebung sein (Test-Setup, kein reales Secret)
    import os

    os.environ["PROXMOX_API_TOKEN"] = "test-wert"
    try:
        response = client.post("/api/v1/integrations/proxmox-1/verify", headers=csrf_headers(client))
    finally:
        del os.environ["PROXMOX_API_TOKEN"]
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["capabilities"]["features"] == ["discover", "health", "metrics"]
    assert body["api_version"] == "8.2"

    # Integration ist nun configured
    detail = client.get("/api/v1/integrations/proxmox-1")
    assert detail.json()["status"] == IntegrationStatus.CONFIGURED.value


def test_verify_endpoint_auth_failure(client: TestClient) -> None:
    client = bootstrap_admin(client)
    client.put(
        "/api/v1/integrations/proxmox-2",
        headers=csrf_headers(client),
        json={"integration_id": "proxmox-2", "name": "x", "adapter": "proxmox", "secret_ref": "NICHT_GESETZT"},
    )
    response = client.post("/api/v1/integrations/proxmox-2/verify", headers=csrf_headers(client))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "auth_failed"
    detail = client.get("/api/v1/integrations/proxmox-2")
    assert detail.json()["status"] == IntegrationStatus.ERROR.value
    assert detail.json()["last_error"]


def test_verify_unknown_integration_404(client: TestClient) -> None:
    client = bootstrap_admin(client)
    response = client.post("/api/v1/integrations/ghost/verify", headers=csrf_headers(client))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
