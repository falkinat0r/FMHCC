"""Read-only-Adapter für vorhandene Loki-Instanzen (Agent 4, R1).

Grenzen (bewusst eng, klar dokumentiert):
- Verifikation (``GET /loki/api/v1/ready`` + Labels-Endpoint), Quellenstatus
  mit Label-Count.
- Keine Log-Inhaltsabfragen in R1: Log-Querying benötigt einen eigenen
  REST-Contract (Vorschlag: docs/proposals/agent4-monitoring-api.md).
- Auth: keine (Standard); optional Bearer/Basic über secret_ref.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx

from app.adapters.base import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterState,
    AdapterStatus,
    ResourceRecord,
    SecretsProvider,
)
from app.adapters.errors import AdapterApiError, AdapterAuthError, AdapterConfigError
from app.integrations.monitoring.base import BaseMonitoringBackend
from app.integrations.monitoring.httputil import build_async_client, request_json
from app.models.integrations import AdapterKind
from app.models.resources import ResourceStatus, ResourceType

__all__ = ["LokiBackend"]


class LokiBackend(BaseMonitoringBackend):
    """Loki HTTP-API als Log-Datenquelle (read-only)."""

    name = "loki"
    kind = AdapterKind.MONITORING

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def _headers(self, config: AdapterConfig, secrets: SecretsProvider) -> dict[str, str]:
        if not config.secret_ref:
            return {}
        secret = secrets.get(config.secret_ref)
        if secret is None:
            raise AdapterAuthError("Loki-Credentials nicht gesetzt (Secret-Referenz ohne Wert)")
        if ":" in secret:
            user, _, password = secret.partition(":")
            token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
            return {"Authorization": f"Basic {token}"}
        return {"Authorization": f"Bearer {secret}"}

    def _client(self, config: AdapterConfig, secrets: SecretsProvider) -> httpx.AsyncClient:
        return build_async_client(config, transport=self._transport, default_headers=self._headers(config, secrets))

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        """Ready-Check + Labels-Endpoint (keine API-Version auslieferbar)."""
        if not config.base_url:
            raise AdapterConfigError("Loki: base_url nicht konfiguriert")
        async with self._client(config, secrets) as client:
            status, _ = await request_json(client, "GET", "/loki/api/v1/ready", raise_for_error=False)
        if status != 200:
            raise AdapterApiError(f"Loki /ready antwortet mit HTTP {status}", http_status=status)
        return AdapterStatus(
            state=AdapterState.OK,
            message="Loki erreichbar (API-Version nicht abfragbar)",
            api_version=None,
            checked_at=datetime.now(UTC),
        )

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        status = await self.verify(config, secrets)
        labels = await self._label_count(config, secrets)
        return AdapterCapabilities(
            features=["verify", "health", "source_status", "discover"],
            api_version=status.api_version,
            extra={"backend": "loki", "labels": labels},
        )

    async def _label_count(self, config: AdapterConfig, secrets: SecretsProvider) -> int:
        async with self._client(config, secrets) as client:
            _, payload = await request_json(client, "GET", "/loki/api/v1/labels")
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return len(payload["data"])
        return 0

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        """Die Loki-Instanz selbst als DASHBOARD-Ressource (Quellenstatus)."""
        if not config.base_url:
            raise AdapterConfigError("Loki: base_url nicht konfiguriert")
        labels = await self._label_count(config, secrets)
        yield ResourceRecord(
            resource_type=ResourceType.DASHBOARD,
            external_id="loki-instance",
            name="Loki",
            status=ResourceStatus.HEALTHY,
            payload={"origin": "loki instance", "labels": labels},
            observed_at=datetime.now(UTC),
        )
