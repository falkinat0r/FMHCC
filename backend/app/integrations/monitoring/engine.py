"""Monitoring-Adapter (registriert, kind='monitoring') — Agent 4, R1.

Ein Adapter pro Integration, davor die Backend-Auswahl für vorhandene
Monitoring-Systeme (Architekturentscheidung: Reuse, keine eigene
Deployment-Stack-Voraussetzung):

- ``extra['backend']``: explizit — 'prometheus' | 'grafana' | 'loki' |
  'uptime_kuma'
- ohne Angabe: Auto-Erkennung über auth-freie Probes (Prometheus,
  Uptime Kuma, Grafana, Loki); nur wenn genau eine Probe eindeutig
  eindeutig auf eine bekannte API antwortet.

Alle Backends sind read-only; ``act`` bleibt nicht_implemented.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from app.adapters.base import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterStatus,
    BaseAdapter,
    MetricsRecord,
    ResourceRecord,
    SecretsProvider,
)
from app.adapters.errors import AdapterConfigError
from app.integrations.monitoring.base import BaseMonitoringBackend
from app.integrations.monitoring.grafana import GrafanaBackend
from app.integrations.monitoring.httputil import build_async_client, request_json
from app.integrations.monitoring.loki import LokiBackend
from app.integrations.monitoring.prometheus import PrometheusBackend
from app.integrations.monitoring.uptime_kuma import UptimeKumaBackend
from app.integrations.registry import register
from app.models.integrations import AdapterKind
from app.models.resources import ResourceType

__all__ = ["MonitoringAdapter", "MonitoringBackendFactory"]

MonitoringBackendFactory = type[BaseMonitoringBackend]


@register
class MonitoringAdapter(BaseAdapter):
    """Adapter für die Integrationssorte 'monitoring' (mehrere Backends)."""

    kind = AdapterKind.MONITORING

    BACKENDS: dict[str, MonitoringBackendFactory] = {
        "prometheus": PrometheusBackend,
        "grafana": GrafanaBackend,
        "loki": LokiBackend,
        "uptime_kuma": UptimeKumaBackend,
    }

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def _backend(self, config: AdapterConfig, secrets: SecretsProvider) -> BaseMonitoringBackend:
        name = config.extra.get("backend")
        if name is None:
            name = await self.detect(config, secrets)
        backend_cls = self.BACKENDS.get(name)
        if backend_cls is None:
            raise AdapterConfigError(
                f"Unbekanntes Monitoring-Backend '{name}'",
                details={"known": sorted(self.BACKENDS)},
            )
        return backend_cls(transport=self._transport)

    async def detect(self, config: AdapterConfig, secrets: SecretsProvider) -> str:
        """Auto-Erkennung über auth-freie Probes (keine Credentials nötig)."""
        if not config.base_url:
            raise AdapterConfigError("Monitoring: base_url nicht konfiguriert")
        async with build_async_client(config, transport=self._transport) as client:
            # Prometheus: /api/v1/status/buildinfo -> {"status":"success",...}
            status, payload = await request_json(client, "GET", "/api/v1/status/buildinfo", raise_for_error=False)
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "success":
                return "prometheus"
            # Uptime Kuma: /api/status -> {"status":"UP"}
            status, payload = await request_json(client, "GET", "/api/status", raise_for_error=False)
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "UP":
                return "uptime_kuma"
            # Grafana: /api/health -> JSON-Objekt (database/version)
            status, payload = await request_json(client, "GET", "/api/health", raise_for_error=False)
            if status == 200 and isinstance(payload, dict) and "database" in payload:
                return "grafana"
            # Loki: /loki/api/v1/labels -> JSON-Array
            status, payload = await request_json(client, "GET", "/loki/api/v1/labels", raise_for_error=False)
            if status == 200 and isinstance(payload, list):
                return "loki"
        raise AdapterConfigError(
            "Monitoring-Backend konnte nicht automatisch erkannt werden; "
            "bitte 'backend' in der Integration konfigurieren",
            details={"known": sorted(self.BACKENDS)},
        )

    # -- IntegrationAdapter-Protokoll (Delegation an gewähltes Backend) ---

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        backend = await self._backend(config, secrets)
        return await backend.verify(config, secrets)

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        backend = await self._backend(config, secrets)
        capabilities = await backend.capabilities(config, secrets)
        capabilities.extra = {**capabilities.extra, "backend": backend.name}
        return capabilities

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        backend = await self._backend(config, secrets)
        async for record in backend.discover(config, secrets):
            yield record

    async def health(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        backend = await self._backend(config, secrets)
        return await backend.health(config, secrets)

    async def collect(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        resource_type: ResourceType,
        external_id: str,
    ) -> MetricsRecord:
        backend = await self._backend(config, secrets)
        return await backend.current_metrics(config, secrets, resource_type, external_id)
