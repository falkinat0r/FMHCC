"""Gemeinsame Fixtures/Helfer der Proxmox-Tests (Agent 3, R1).

Konvention:
- Alle Anfragen laufen ueber ``httpx.MockTransport`` (kein Netzwerk).
- Token-Value ist ein dokumentierter Test-Placeholder (kein echtes Secret).
- Rate-Limiter/Retry sind auf Testwerte gesetzt (schnell, kein Sleep).
- Registry wird pro Test auf den echten Proxmox-Adapter gesetzt und
  danach zurueckgesetzt (R0-Testbasis bleibt unangetastet).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from app.adapters.base import AdapterConfig, ResourceRecord
from app.adapters.secrets import EnvSecretsProvider
from app.integrations import registry
from app.integrations.proxmox.adapter import register_proxmox_adapter
from app.integrations.proxmox.client import ProxmoxClient, set_test_transport
from app.integrations.proxmox.config import ProxmoxOptions, ProxmoxToken, build_options, parse_token
from tests.proxmox.fixtures import FakeProxmoxServer, standalone_scenario

BASE_URL = "https://pve.test.lan:8006"
SECRET_REF = "HCC_TEST_PROXMOX_TOKEN"
# Test-Placeholder im PVE-Format <user>@<realm>!<token-id>=<secret> (kein echtes Secret)
TOKEN_VALUE = "hcc@pve!hcc-test=0123456789abcdef01234789abcdef012345"


@pytest.fixture(autouse=True)
def _proxmox_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legt die Test-Secret-Variable an (fuer EnvSecretsProvider())."""
    monkeypatch.setenv(SECRET_REF, TOKEN_VALUE)


@pytest.fixture(autouse=True)
def _registry() -> None:
    """Registry pro Test: nur der echte Proxmox-Adapter (idempotent)."""
    registry._reset_for_tests()
    register_proxmox_adapter()
    yield
    registry._reset_for_tests()


@pytest.fixture()
def server() -> FakeProxmoxServer:
    """Standard-Szenario: Standalone-Host (Tests duerfen es ueberschreiben)."""
    return standalone_scenario()


@pytest.fixture()
def transport(server: FakeProxmoxServer) -> httpx.MockTransport:
    """Globaler Test-Transport (fuer Adapter-/API-Pfade ohne expliziten Transport)."""
    mock = httpx.MockTransport(server.handle)
    set_test_transport(mock)
    yield mock
    set_test_transport(None)


def make_config(**extra: str) -> AdapterConfig:
    """AdapterConfig mit Test-Defaults (hohes Rate-Limit, minimales Retry-Backoff)."""
    return AdapterConfig(
        base_url=BASE_URL,
        secret_ref=SECRET_REF,
        extra={
            "rate_limit_per_second": "1000",
            "max_retries": "1",
            "retry_backoff_seconds": "0.01",
            **extra,
        },
    )


def make_options(**extra: str) -> ProxmoxOptions:
    return build_options(make_config(**extra))


def make_token() -> ProxmoxToken:
    return parse_token(TOKEN_VALUE)


def make_client(server: FakeProxmoxServer, **extra: str) -> ProxmoxClient:
    """Client mit explizitem MockTransport (kein globaler Test-Transport)."""
    return ProxmoxClient(make_options(**extra), make_token(), transport=httpx.MockTransport(server.handle))


def run(coro: Awaitable[Any]) -> Any:
    """Synchrone Test-Wrapper fuer async Code (R0-Konvention, kein pytest-asyncio)."""
    return asyncio.run(coro)


def client_request(server: FakeProxmoxServer, fn: Callable[[ProxmoxClient], Awaitable[Any]], **extra: str) -> Any:
    """Fuehrt ``fn(client)`` in einem ``async with ProxmoxClient``-Block aus."""

    async def _runner() -> Any:
        async with make_client(server, **extra) as client:
            return await fn(client)

    return run(_runner())


def discover_records(server: FakeProxmoxServer, **extra: str) -> list[ResourceRecord]:
    """Fuehrt die Proxmox-Discovery gegen den Fake-Server aus (expliziter Transport)."""
    from app.integrations.proxmox.discovery import ProxmoxDiscovery

    async def _runner() -> list[ResourceRecord]:
        client = make_client(server, **extra)
        try:
            discovery = ProxmoxDiscovery(client, fetch_details=make_options(**extra).fetch_resource_details)
            return [record async for record in discovery.discover()]
        finally:
            await client.aclose()

    return run(_runner())


def audit_actions(db: Any) -> list[str]:
    """Alle Audit-Actions der aktuellen Session."""
    from sqlalchemy import select

    from app.models.audit import AuditEvent

    return [event.action for event in db.scalars(select(AuditEvent)).all()]


def make_secrets() -> EnvSecretsProvider:
    return EnvSecretsProvider({SECRET_REF: TOKEN_VALUE})


def make_integration(db: Any, *, integration_id: str = "pve-test") -> Any:
    """Legt eine (konfigurierte) Proxmox-Integration an; liefert sie, falls vorhanden."""
    from sqlalchemy import select

    from app.models.integrations import AdapterKind, Integration, IntegrationStatus

    existing = db.scalar(select(Integration).where(Integration.integration_id == integration_id))
    if existing is not None:
        return existing
    integration = Integration(
        integration_id=integration_id,
        name="Proxmox (Test-Fixture)",
        adapter=AdapterKind.PROXMOX,
        base_url=BASE_URL,
        secret_ref=SECRET_REF,
        status=IntegrationStatus.CONFIGURED,
        capabilities={},
    )
    db.add(integration)
    db.flush()
    return integration
