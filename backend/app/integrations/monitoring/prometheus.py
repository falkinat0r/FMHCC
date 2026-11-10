"""Read-only-Adapter für vorhandene Prometheus-Instanzen (Agent 4, R1).

Architekturentscheidung: **Reuse** — HCC setzt keine Prometheus-Installation
voraus; es wird nur die HTTP-Query-API (``/api/v1/…``) einer vorhandenen
Instanz angebunden, optional mit Basic-Auth (``user:pass``) oder Bearer-Token.

Sicherheit:
- **Keine freie PromQL-Ausführung** aus Frontend-Eingaben: ausschließlich
  statische, validierte Query-Templates (METRIC_TEMPLATES). Ergebnisse werden
  client-seitig über Label-Values gefiltert (Whitelist-Regex, keine
  serverseitige Interpolation).
- Keine Schreib-Endpoints. Keine Alert-Evaluierung.
- Optional: Active Alerts aus einem vorhandenen Alertmanager
  (``extra['alertmanager_url']``, administrativ verwaltet).
"""

from __future__ import annotations

import base64
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.adapters.base import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterState,
    AdapterStatus,
    MetricsRecord,
    MetricValue,
    ResourceRecord,
    SecretsProvider,
)
from app.adapters.errors import (
    AdapterApiError,
    AdapterAuthError,
    AdapterConfigError,
    AdapterError,
)
from app.integrations.monitoring.base import (
    TIME_RANGE_SECONDS,
    TIME_RANGE_STEP_SECONDS,
    AlertStatus,
    BaseMonitoringBackend,
    NormalizedAlert,
    ResourceAvailability,
    ResourceRef,
    ServiceAvailability,
    TimeRange,
    TimeSeries,
    TimeSeriesPoint,
)
from app.integrations.monitoring.events import EventDeduplicator, NormalizedEvent, severity_from_raw
from app.integrations.monitoring.httputil import build_async_client, request_json
from app.models.resources import ResourceStatus, ResourceType

__all__ = ["MetricTemplate", "PrometheusBackend", "container_templates", "host_templates"]

#: Whitelist für Label-Keys/-Values (nur client-seitiges Filtern).
_LABEL_KEY_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_LABEL_VALUE_RE = re.compile(r"^[A-Za-z0-9._:/\[\]-]*$")

#: Obergrenze für Discover (Instances), damit eine Instanz mit tausenden
#: Targets das Inventar nicht sprengt.
_MAX_DISCOVERED_INSTANCES = 500


def host_templates() -> tuple[MetricTemplate, ...]:
    """Node-Exporter-Templates für Host-Ressourcen (filtert über 'instance')."""
    return (
        MetricTemplate("up", "up", "ratio", "Target-Verfügbarkeit (1=up, 0=down)", "instance"),
        MetricTemplate(
            "cpu_percent",
            '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
            "percent",
            "CPU-Auslastung (5m-Mittel)",
            "instance",
        ),
        MetricTemplate(
            "memory_percent",
            "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)",
            "percent",
            "Speicherauslastung",
            "instance",
        ),
        MetricTemplate(
            "memory_available_bytes", "node_memory_MemAvailable_bytes", "bytes", "Verfügbarer Speicher", "instance"
        ),
        MetricTemplate("load1", "node_load1", "ratio", "Load Average (1 min)", "instance"),
        MetricTemplate("load5", "node_load5", "ratio", "Load Average (5 min)", "instance"),
        MetricTemplate(
            "disk_root_percent",
            '100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})',
            "percent",
            "Root-Dateisystem-Auslastung",
            "instance",
        ),
    )


def container_templates() -> tuple[MetricTemplate, ...]:
    """cAdvisor-Templates für Container-Ressourcen (filtert über 'name')."""
    return (
        MetricTemplate(
            "cpu_cores",
            'sum by (name) (rate(container_cpu_usage_seconds_total{name!=""}[5m]))',
            "cores",
            "CPU-Verbrauch (in Cores)",
            "name",
        ),
        MetricTemplate(
            "memory_bytes", 'container_memory_working_set_bytes{name!=""}', "bytes", "Container-Speicher (working set)", "name"
        ),
    )


def _templates_by_resource_type(resource_type: ResourceType) -> tuple[MetricTemplate, ...] | None:
    if resource_type is ResourceType.HOST:
        return host_templates()
    if resource_type is ResourceType.CONTAINER:
        return container_templates()
    return None


@dataclass(frozen=True)
class MetricTemplate:
    """Statisches, validiertes Query-Template (keine freie PromQL).

    Frozen-Dataclass (keine Pydantic-Validierung zur Laufzeit nötig:
    Templates sind Code, keine Nutzer-Eingabe).
    """

    name: str
    promql: str
    unit: str | None = None
    description: str = ""
    filter_label: str = "instance"


def _all_templates() -> dict[str, MetricTemplate]:
    templates: dict[str, MetricTemplate] = {}
    for template in (*host_templates(), *container_templates()):
        templates[template.name] = template
    return templates


def validate_label_key(key: str) -> None:
    if not _LABEL_KEY_RE.fullmatch(key):
        raise AdapterConfigError(f"Ungültiger Label-Key '{key}'", details={"label": key})


def validate_label_value(value: str) -> None:
    """Whitelist für Label-Values (Ziel-/Instanz-Identifikatoren).

    Zusätzlich: keine Path-Traversal-Sequenzen ('..' oder führendes '.'),
    auch wenn die Zeichen einzeln erlaubt wären — Instanz-Labels sind
    Host[:Port]-Identifier, keine Pfade.
    """
    if not value or len(value) > 256 or not _LABEL_VALUE_RE.fullmatch(value):
        raise AdapterConfigError(
            "Ungültiger Label-Value (erlaubt: Buchstaben, Ziffern, . _ : / - [ ])",
            details={"label": value[:64]},
        )
    if value.startswith(".") or ".." in value:
        raise AdapterConfigError(
            "Ungültiger Label-Value (Path-Traversal-Sequenzen sind nicht erlaubt)",
            details={"label": value[:64]},
        )


def _iter_series(data: Any) -> list[dict[str, Any]]:
    """Liefert die Series-Liste einer Prometheus-Instant-/Range-Query.

    Instant-/Range-Queries antworten mit ``data = {"resultType": ..., "result": [series]}``;
    Label-Value-Queries mit ``data = [value]``. Die Series liegen also in
    ``result`` (falls vorhanden).
    """
    if isinstance(data, dict):
        data = data.get("result")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _parse_ts(raw: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(raw), tz=UTC)
    except (TypeError, ValueError):
        return None


def _parse_value(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN/Inf -> unbrauchbar
        return None
    return value


class PrometheusBackend(BaseMonitoringBackend):
    """Prometheus-Query-API als Monitoring-Backend (read-only)."""

    name = "prometheus"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    # -- Client/Auth ----------------------------------------------------

    def _headers(self, config: AdapterConfig, secrets: SecretsProvider) -> dict[str, str]:
        """Auth: Secret-Wert 'user:pass' -> Basic; sonst Bearer; sonst none."""
        if not config.secret_ref:
            return {}
        secret = secrets.get(config.secret_ref)
        if secret is None:
            raise AdapterAuthError("Credentials nicht gesetzt (Secret-Referenz ohne Wert)")
        if ":" in secret:
            user, _, password = secret.partition(":")
            token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
            return {"Authorization": f"Basic {token}"}
        return {"Authorization": f"Bearer {secret}"}

    def _client(self, config: AdapterConfig, secrets: SecretsProvider) -> httpx.AsyncClient:
        return build_async_client(config, transport=self._transport, default_headers=self._headers(config, secrets))

    @staticmethod
    def _require_base_url(config: AdapterConfig) -> None:
        if not config.base_url:
            raise AdapterConfigError("Prometheus: base_url nicht konfiguriert")

    @staticmethod
    def _query_data(payload: object, *, path: str) -> Any:
        """Prometheus-Antwort dekodieren; Fehlerantwort -> AdapterApiError."""
        if not isinstance(payload, dict):
            raise AdapterApiError(f"Unerwartete Antwort-Form bei {path}")
        status = str(payload.get("status", ""))
        if status == "error":
            raise AdapterApiError(
                f"Query-Fehler bei {path}: {str(payload.get('error', ''))[:256]}",
                details={"error_type": str(payload.get("errorType", ""))},
            )
        if status != "success":
            raise AdapterApiError(f"Unerwarteter Status '{status}' bei {path}")
        return payload.get("data")

    # -- IntegrationAdapter-Protokoll -----------------------------------

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        self._require_base_url(config)
        async with self._client(config, secrets) as client:
            _, payload = await request_json(client, "GET", "/api/v1/status/buildinfo")
        data = self._query_data(payload, path="/api/v1/status/buildinfo")
        version = str(data.get("version", "")) if isinstance(data, dict) else ""
        if not version:
            raise AdapterApiError("Prometheus: buildinfo ohne Versionsangabe")
        return AdapterStatus(
            state=AdapterState.OK,
            message=f"Prometheus {version} erreichbar",
            api_version=version,
            checked_at=datetime.now(UTC),
        )

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        status = await self.verify(config, secrets)
        return AdapterCapabilities(
            features=[
                "verify",
                "health",
                "source_status",
                "discover",
                "metrics",
                "historical",
                "availability",
                "alerts",
            ],
            api_version=status.api_version,
            extra={"backend": "prometheus"},
        )

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        """Monitoring-Targets (Label-Value 'instance') als HOST-Ressourcen."""
        self._require_base_url(config)
        async with self._client(config, secrets) as client:
            _, payload = await request_json(client, "GET", "/api/v1/label/instance/values")
        data = self._query_data(payload, path="/api/v1/label/instance/values")
        values = [str(v) for v in (data if isinstance(data, list) else [])][: _MAX_DISCOVERED_INSTANCES]
        now = datetime.now(UTC)
        for value in values:
            yield ResourceRecord(
                resource_type=ResourceType.HOST,
                external_id=value,
                name=value,
                status=ResourceStatus.UNKNOWN,
                payload={"instance": value, "origin": "prometheus instance label"},
                observed_at=now,
            )

    async def health(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        return await self.verify(config, secrets)

    async def current_metrics(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        resource_type: ResourceType,
        external_id: str,
    ) -> MetricsRecord:
        templates = _templates_by_resource_type(resource_type)
        if templates is None:
            raise AdapterError(
                message=f"Keine Metrik-Templates für Ressourcentyp '{resource_type.value}'",
                state=AdapterState.NOT_IMPLEMENTED,
            )
        validate_label_value(external_id)
        metrics: dict[str, MetricValue] = {}
        async with self._client(config, secrets) as client:
            for template in templates:
                _, payload = await request_json(
                    client, "GET", "/api/v1/query", params={"query": template.promql}
                )
                data = self._query_data(payload, path="/api/v1/query")
                for series in _iter_series(data):
                    labels = series.get("metric")
                    labels = labels if isinstance(labels, dict) else {}
                    if labels.get(template.filter_label) != external_id:
                        continue
                    vector = series.get("value")
                    if not isinstance(vector, list) or len(vector) != 2:
                        continue
                    value = _parse_value(vector[1])
                    if value is None:
                        continue
                    metrics[template.name] = MetricValue(value=value, unit=template.unit)
                    break
        return MetricsRecord(
            external_id=external_id,
            resource_type=resource_type,
            metrics=metrics,
            collected_at=datetime.now(UTC),
        )

    async def historical_metrics(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        metric: str,
        labels: dict[str, str],
        range: TimeRange,
    ) -> list[TimeSeries]:
        template = _all_templates().get(metric)
        if template is None:
            raise AdapterConfigError(f"Unbekanntes Metrik-Template '{metric}'")
        for key, value in labels.items():
            validate_label_key(key)
            validate_label_value(value)

        end = datetime.now(UTC)
        start = end - timedelta(seconds=TIME_RANGE_SECONDS[range])
        step = TIME_RANGE_STEP_SECONDS[range]
        async with self._client(config, secrets) as client:
            _, payload = await request_json(
                client,
                "GET",
                "/api/v1/query_range",
                params={
                    "query": template.promql,
                    "start": int(start.timestamp()),
                    "end": int(end.timestamp()),
                    "step": step,
                },
            )
        data = self._query_data(payload, path="/api/v1/query_range")
        series: list[TimeSeries] = []
        for item in _iter_series(data):
            item_labels = item.get("metric")
            item_labels = {str(k): str(v) for k, v in item_labels.items()} if isinstance(item_labels, dict) else {}
            if any(item_labels.get(k) != v for k, v in labels.items()):
                continue
            raw_values = item.get("values")
            raw_values = raw_values if isinstance(raw_values, list) else []
            points: list[TimeSeriesPoint] = []
            for pair in raw_values:
                if not isinstance(pair, list) or len(pair) != 2:
                    continue
                timestamp = _parse_ts(pair[0])
                value = _parse_value(pair[1])
                if timestamp is None or value is None:
                    continue
                points.append(TimeSeriesPoint(timestamp=timestamp, value=value, unit=template.unit))
            series.append(
                TimeSeries(metric=template.name, labels=item_labels, unit=template.unit, points=points)
            )
        return series

    async def host_availability(self, config: AdapterConfig, secrets: SecretsProvider) -> list[ResourceAvailability]:
        """Targets aus 'up' -> Host-Verfügbarkeit (1=healthy, sonst down)."""
        async with self._client(config, secrets) as client:
            _, payload = await request_json(client, "GET", "/api/v1/query", params={"query": "up"})
        data = self._query_data(payload, path="/api/v1/query")
        now = datetime.now(UTC)
        out: list[ResourceAvailability] = []
        for item in _iter_series(data):
            labels = item.get("metric")
            labels = labels if isinstance(labels, dict) else {}
            instance = str(labels.get("instance", ""))
            if not instance:
                continue
            vector = item.get("value")
            value = _parse_value(vector[1]) if isinstance(vector, list) and len(vector) == 2 else None
            if value is None:
                status = ResourceStatus.UNKNOWN
                detail = None
            else:
                status = ResourceStatus.HEALTHY if value == 1 else ResourceStatus.DOWN
                detail = f"up={value:g}"
            out.append(
                ResourceAvailability(
                    resource_type=ResourceType.HOST,
                    external_id=instance,
                    name=instance,
                    status=status,
                    checked_at=now,
                    detail=detail,
                )
            )
        return out

    async def service_availability(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> list[ServiceAvailability]:
        """Prometheus-Targets = Services (gleiche 'up'-Logik wie host_availability)."""
        hosts = await self.host_availability(config, secrets)
        return [
            ServiceAvailability(service=host.name or host.external_id, status=host.status, checked_at=host.checked_at, detail=host.detail)
            for host in hosts
        ]

    async def events(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[NormalizedEvent]:
        """Prometheus selbst erzeugt keine Events; Alertmanager-Alerts siehe alerts()."""
        async for event in super().events(config, secrets):
            yield event

    async def alerts(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[NormalizedAlert]:
        """Active Alerts aus vorhandenem Alertmanager (optional konfiguriert)."""
        am_url = config.extra.get("alertmanager_url")
        if not am_url:
            async for alert in super().alerts(config, secrets):
                yield alert
            return
        dedup = EventDeduplicator()
        now = datetime.now(UTC)
        async with build_async_client(config, transport=self._transport, base_url=am_url) as client:
            status, payload = await request_json(client, "GET", "/api/v2/alerts", raise_for_error=False)
        if status != 200 or not isinstance(payload, list):
            # Ehrlich: Alertmanager ohne Auth/ohne v2-API -> keine Alerts, kein Fehler.
            async for alert in super().alerts(config, secrets):
                yield alert
            return
        for item in payload:
            if not isinstance(item, dict):
                continue
            labels = {str(k): str(v) for k, v in (item.get("labels") or {}).items()}
            annotations = {str(k): str(v) for k, v in (item.get("annotations") or {}).items()}
            instance = labels.get("instance")
            resource = (
                ResourceRef(resource_type=ResourceType.HOST, external_id=instance, name=instance)
                if instance
                else None
            )
            name = labels.get("alertname", "unknown")
            alert = NormalizedAlert(
                fingerprint=f"alertmanager:{labels.get('fingerprint', name)}",
                source="alertmanager",
                source_alert_id=labels.get("fingerprint"),
                severity=severity_from_raw(labels.get("severity")),
                name=name,
                summary=annotations.get("summary") or annotations.get("description"),
                status=AlertStatus.ACTIVE,
                resource=resource,
                labels=labels,
                started_at=_parse_ts(item.get("startsAt")),
                received_at=now,
            )
            if dedup.is_new(alert):
                yield alert
