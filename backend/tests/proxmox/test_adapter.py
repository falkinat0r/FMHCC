"""Adapter-/Registry-/API-Tests (Agent 3, R1).

Deckung: explizite Registrierung (idempotent, keine Kollision mit
fremden Proxmox-Adaptiern), IntegrationAdapter-Protokoll, health/collect,
Discover ueber den Adapter, und der eingefrorene Verify-Endpunkt
(POST /api/v1/integrations/{id}/verify) gegen den Fake-Server.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.base import AdapterConfig, AdapterState, BaseAdapter, IntegrationAdapter
from app.adapters.errors import AdapterError
from app.integrations import registry
from app.integrations.proxmox.adapter import ProxmoxAdapter, register_proxmox_adapter
from app.models.integrations import AdapterKind, IntegrationStatus
from app.models.resources import ResourceType
from tests.conftest import bootstrap_admin, csrf_headers
from tests.proxmox.conftest import BASE_URL, SECRET_REF, make_config, make_secrets, run


class _ForeignProxmox(BaseAdapter):
    """Bewusst fremder Proxmox-Adapter (simuliert die R0-Test-Fixture)."""

    kind = AdapterKind.PROXMOX

    async def verify(self, config: AdapterConfig, secrets) -> None:  # pragma: no cover
        raise NotImplementedError

    async def capabilities(self, config: AdapterConfig, secrets) -> None:  # pragma: no cover
        raise NotImplementedError

    async def discover(self, config: AdapterConfig, secrets):  # pragma: no cover
        if False:
            yield  # type: ignore[misc]


# ---------------------------------------------------------------------- registry


def test_register_idempotent() -> None:
    register_proxmox_adapter()
    register_proxmox_adapter()  # zweiter Aufruf darf nicht werfen
    assert registry.get_adapter(AdapterKind.PROXMOX) is ProxmoxAdapter


def test_register_yields_to_foreign_adapter() -> None:
    # Simuliert die R0-Situation: FakeAdapter (kind=proxmox) ist bereits da
    registry._reset_for_tests()
    registry.register(_ForeignProxmox)

    register_proxmox_adapter()  # muss KEIN ValueError werfen

    assert registry.get_adapter(AdapterKind.PROXMOX) is _ForeignProxmox
    # und ein zweiter Versuch auch nicht
    register_proxmox_adapter()
    assert registry.get_adapter(AdapterKind.PROXMOX) is _ForeignProxmox


def test_adapter_satisfies_frozen_protocol() -> None:
    assert isinstance(ProxmoxAdapter(), IntegrationAdapter)
    assert ProxmoxAdapter.kind is AdapterKind.PROXMOX


# ------------------------------------------------------------------ adapter API


def test_health_ok(transport) -> None:
    status = run(ProxmoxAdapter().health(make_config(), make_secrets()))
    assert status.state is AdapterState.OK
    assert status.api_version == "9.1.2"


def test_health_unreachable_raises(transport, server) -> None:
    server.network_error = "unreachable"
    with pytest.raises(AdapterError) as exc_info:
        run(ProxmoxAdapter().health(make_config(), make_secrets()))
    assert exc_info.value.state is AdapterState.UNREACHABLE


def test_health_missing_version_data_is_api_error(transport, server) -> None:
    # /version liefert unerwartet keine Version (Data None) => API_ERROR
    server.version = None
    status = run(ProxmoxAdapter().health(make_config(), make_secrets()))
    assert status.state is AdapterState.API_ERROR


def test_collect_not_implemented() -> None:
    adapter = ProxmoxAdapter()
    with pytest.raises(AdapterError) as exc_info:
        run(adapter.collect(make_config(), make_secrets(), ResourceType.VM, "101"))
    assert exc_info.value.state is AdapterState.NOT_IMPLEMENTED


def test_discover_via_adapter_uses_global_transport(transport) -> None:
    async def _drain():
        return [record async for record in ProxmoxAdapter().discover(make_config(), make_secrets())]

    records = run(_drain())
    assert [record.external_id for record in records] == ["pve1", "101", "102", "103", "201", "202"]


def test_discover_without_transport_or_config_fails_cleanly() -> None:
    """Ohne base_url: AdapterConfigError (nicht_configured), keine Exception-Salat."""
    from app.adapters.errors import AdapterConfigError

    config = AdapterConfig(base_url=None, secret_ref=SECRET_REF)
    with pytest.raises(AdapterConfigError) as exc_info:
        run(ProxmoxAdapter().verify(config, make_secrets()))
    assert exc_info.value.state is AdapterState.NOT_CONFIGURED


# ------------------------------------------------------------- HTTP verify flow


def _configure_integration(client: TestClient) -> None:
    response = client.put(
        "/api/v1/integrations/pve-test",
        headers=csrf_headers(client),
        json={
            "integration_id": "pve-test",
            "name": "Proxmox (Test-Fixture)",
            "adapter": "proxmox",
            "base_url": BASE_URL,
            "secret_ref": SECRET_REF,
        },
    )
    assert response.status_code == 200, response.text


def test_verify_endpoint_success(client: TestClient, transport, server) -> None:
    client = bootstrap_admin(client)
    _configure_integration(client)
    # Transport-Fixture muss vor dem Verify gesetzt sein (global, Adapter baut Client selbst)
    assert server.version["version"] == "9.1.2"

    response = client.post("/api/v1/integrations/pve-test/verify", headers=csrf_headers(client))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["api_version"] == "9.1.2"
    assert body["capabilities"]["cluster_mode"] == "standalone"
    assert "discover" in body["capabilities"]["features"]
    assert "act:start" in body["capabilities"]["features"]

    detail = client.get("/api/v1/integrations/pve-test")
    assert detail.json()["status"] == IntegrationStatus.CONFIGURED.value
    assert detail.json()["secret_ref"] == SECRET_REF  # Admin sieht die Referenz (nie den Wert)


def test_verify_endpoint_invalid_token_format(client: TestClient, transport, monkeypatch) -> None:
    client = bootstrap_admin(client)
    monkeypatch.setenv(SECRET_REF, "kein-gueltiges-token-format")
    _configure_integration(client)

    response = client.post("/api/v1/integrations/pve-test/verify", headers=csrf_headers(client))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "not_configured"

    detail = client.get("/api/v1/integrations/pve-test")
    assert detail.json()["status"] == IntegrationStatus.ERROR.value
    assert detail.json()["last_error"]
    # Kein Secret-Wert in der Fehlermeldung
    assert "kein-gueltiges-token-format" not in detail.json()["last_error"]


def test_verify_endpoint_wrong_secret(client: TestClient, transport, monkeypatch) -> None:
    client = bootstrap_admin(client)
    monkeypatch.setenv(SECRET_REF, "hcc@pve!hcc-test=ffffffffffffffffffffffffffffffff")
    _configure_integration(client)

    response = client.post("/api/v1/integrations/pve-test/verify", headers=csrf_headers(client))
    assert response.status_code == 200
    assert response.json()["status"] == "auth_failed"

    detail = client.get("/api/v1/integrations/pve-test")
    assert detail.json()["status"] == IntegrationStatus.ERROR.value


def test_verify_endpoint_unreachable(client: TestClient, transport, server) -> None:
    client = bootstrap_admin(client)
    server.network_error = "unreachable"
    _configure_integration(client)

    response = client.post("/api/v1/integrations/pve-test/verify", headers=csrf_headers(client))
    assert response.status_code == 200
    assert response.json()["status"] == "unreachable"


def test_verify_endpoint_version_gate(client: TestClient, transport, server) -> None:
    client = bootstrap_admin(client)
    server.version = {"version": "7.4.1", "release": "7.4.1"}
    _configure_integration(client)

    response = client.post("/api/v1/integrations/pve-test/verify", headers=csrf_headers(client))
    assert response.status_code == 200
    assert response.json()["status"] == "version_unsupported"


def test_verify_endpoint_unknown_adapter_is_not_implemented(client: TestClient) -> None:
    """Adapter ohne Registrierung antwortet ehrlich mit not_implemented (kein Stub)."""
    client = bootstrap_admin(client)
    response = client.put(
        "/api/v1/integrations/ghost-tail",
        headers=csrf_headers(client),
        json={
            "integration_id": "ghost-tail",
            "name": "Ghost",
            "adapter": "tailscale",
            "base_url": "https://tail.example.lan:1100",
        },
    )
    assert response.status_code == 200, response.text
    verify = client.post("/api/v1/integrations/ghost-tail/verify", headers=csrf_headers(client))
    assert verify.status_code == 200
    assert verify.json()["status"] == "not_implemented"
    assert "registriert" in (verify.json()["message"] or "")


def test_verify_endpoint_requires_admin(client: TestClient) -> None:
    """Verify ist admin-only (RBAC frozen Key integrations.manage)."""
    client = bootstrap_admin(client)
    _configure_integration(client)

    # Viewer anlegen und mit Viewer-Session verifizieren
    from tests.conftest import VIEWER_PASSWORD, VIEWER_USERNAME, create_viewer

    create_viewer(client, csrf_headers(client))
    response = client.post(
        "/api/v1/auth/login", json={"username": VIEWER_USERNAME, "password": VIEWER_PASSWORD}
    )
    assert response.status_code == 200

    verify = client.post("/api/v1/integrations/pve-test/verify", headers=csrf_headers(client))
    assert verify.status_code == 403
    assert verify.json()["error"]["code"] == "forbidden"
