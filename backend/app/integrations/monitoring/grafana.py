"""Read-only-Adapter für vorhandene Grafana-Instanzen (Agent 4, R1).

Grenzen (bewusst eng, klar dokumentiert):
- Verbindung/Health (``GET /api/health``), API-Version, Datenquellen-Liste
  (``GET /api/datasources``) — Metrik-Abfragen laufen direkt über das
  Prometheus-Backend, nicht über Grafana-Proxy.
- Auth: Service-Account-Token (Bearer) über secret_ref; ohne Token nur
  wenn die Instanz offen ist.
- Keine Alert-/Dashboard-Inhalte, keine Schreibanfänge.
"""

from __future__ import annotations

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
from app.adapters.errors import AdapterAuthError, AdapterConfigError
from app.integrations.monitoring.base import BaseMonitoringBackend
from app.integrations.monitoring.httputil import build_async_client, request_json
from app.models.integrations import AdapterKind
from app.models.resources import ResourceStatus, ResourceType

__all__ = ["GrafanaBackend"]


class GrafanaBackend(BaseMonitoringBackend):
    """Grafana HTTP-API als Monitoring-Backend (read-only)."""

    name = "grafana"
    kind = AdapterKind.MONITORING

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def _headers(self, config: AdapterConfig, secrets: SecretsProvider) -> dict[str, str]:
        if not config.secret_ref:
            return {}
        token = secrets.get(config.secret_ref)
        if token is None:
            raise AdapterAuthError("Grafana-Token nicht gesetzt (Secret-Referenz ohne Wert)")
        return {"Authorization": f"Bearer {token}"}

    def _client(self, config: AdapterConfig, secrets: SecretsProvider) -> httpx.AsyncClient:
        return build_async_client(config, transport=self._transport, default_headers=self._headers(config, secrets))

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        if not config.base_url:
            raise AdapterConfigError("Grafana: base_url nicht konfiguriert")
        async with self._client(config, secrets) as client:
            _, payload = await request_json(client, "GET", "/api/health")
        health = payload if isinstance(payload, dict) else {}
        database = str(health.get("database", ""))
        if database and database != "ok":
            return AdapterStatus(
                state=AdapterState.API_ERROR,
                message=f"Grafana-DB-Status '{database}'",
                checked_at=datetime.now(UTC),
            )
        version = health.get("version")
        return AdapterStatus(
            state=AdapterState.OK,
            message="Grafana erreichbar",
            api_version=str(version) if version else None,
            checked_at=datetime.now(UTC),
        )

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        status = await self.verify(config, secrets)
        return AdapterCapabilities(
            features=["verify", "health", "source_status", "discover"],
            api_version=status.api_version,
            extra={"backend": "grafana"},
        )

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        """Grafana-Instanz + konfigurierte Datenquellen als DASHBOARD-Ressourcen."""
        if not config.base_url:
            raise AdapterConfigError("Grafana: base_url nicht konfiguriert")
        now = datetime.now(UTC)
        yield ResourceRecord(
            resource_type=ResourceType.DASHBOARD,
            external_id="grafana-instance",
            name="Grafana",
            status=ResourceStatus.HEALTHY,
            payload={"origin": "grafana instance"},
            observed_at=now,
        )
        async with self._client(config, secrets) as client:
            _, payload = await request_json(client, "GET", "/api/datasources")
        datasources = payload if isinstance(payload, list) else []
        for source in datasources[:200]:
            if not isinstance(source, dict):
                continue
            source_id = source.get("id")
            if source_id is None:
                continue
            name = str(source.get("name", f"datasource-{source_id}"))
            source_type = str(source.get("type", "unknown"))
            yield ResourceRecord(
                resource_type=ResourceType.DASHBOARD,
                external_id=f"datasource-{source_id}",
                name=name,
                status=ResourceStatus.UNKNOWN,
                payload={"origin": "grafana datasource", "type": source_type},
                observed_at=now,
            )
