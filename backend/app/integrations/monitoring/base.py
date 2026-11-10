"""Monitoring-Abstraktion: einheitliche Schnittstelle ueber vorhandene
Monitoring-Systeme (Agent 4, R1).

Wichtigste Architekturentscheidung: **Reuse** — HCC stellt nicht die
Installation von Prometheus/Grafana/Loki/Uptime Kuma in Aussicht; der
Adapter bindet nur vorhandene Instanzen an. Jede Quelle ist abschaltbar;
fehlende Daten => ``unknown``/``not_configured``, niemals Zufallswerte.

Die Schnittstelle deckt ab:
- aktuelle Ressourcenmetriken (``current_metrics``, Einheiten + UTC)
- historische Zeitreihen (``historical_metrics``, Zeiträume 1h/6h/24h/7d/30d)
- Host-Verfuegbarkeit (``host_availability``)
- Service-Verfuegbarkeit (``service_availability``)
- Events (``events``, einheitliches NormalizedEvent-Modell)
- Alerts (``alerts``, NormalizedAlert)
- Datenquellenstatus (``source_status``, Source-Freshness + API-Version)

Ressourcen-Identitaet folgt dem frozen Inventar-Contract:
``(integration_id, resource_type, external_id)``.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.adapters.base import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterState,
    AdapterStatus,
    MetricsRecord,
    ResourceRecord,
    SecretsProvider,
)
from app.adapters.errors import AdapterError
from app.models.integrations import AdapterKind
from app.models.resources import ResourceStatus, ResourceType

__all__ = [
    "AlertStatus",
    "BaseMonitoringBackend",
    "DataSourceStatus",
    "EventSeverity",
    "MonitoringBackend",
    "NormalizedAlert",
    "ResourceAvailability",
    "ResourceRef",
    "ServiceAvailability",
    "TimeRange",
    "TimeSeries",
    "TimeSeriesPoint",
    "TIME_RANGE_SECONDS",
    "TIME_RANGE_STEP_SECONDS",
]


class TimeRange(StrEnum):
    """Standard-Zeitfenster (MASTER_PROMPT: 1h/6h/24h/7d/30d)."""

    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    ONE_DAY = "24h"
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"


TIME_RANGE_SECONDS: dict[TimeRange, int] = {
    TimeRange.ONE_HOUR: 3_600,
    TimeRange.SIX_HOURS: 21_600,
    TimeRange.ONE_DAY: 86_400,
    TimeRange.SEVEN_DAYS: 604_800,
    TimeRange.THIRTY_DAYS: 2_592_000,
}

#: Empfohlener Query-Schritt pro Zeitfenster (halte Punktzahl ~<500).
TIME_RANGE_STEP_SECONDS: dict[TimeRange, int] = {
    TimeRange.ONE_HOUR: 60,
    TimeRange.SIX_HOURS: 120,
    TimeRange.ONE_DAY: 300,
    TimeRange.SEVEN_DAYS: 900,
    TimeRange.THIRTY_DAYS: 3_600,
}


class TimeSeriesPoint(BaseModel):
    """Ein Zeitwert (Timestamp immer UTC)."""

    timestamp: datetime
    value: float
    unit: str | None = None


class TimeSeries(BaseModel):
    """Historische Zeitreihe einer Metrik (ein Label-Satz)."""

    metric: str
    labels: dict[str, str] = Field(default_factory=dict)
    unit: str | None = None
    points: list[TimeSeriesPoint] = Field(default_factory=list)


class DataSourceStatus(BaseModel):
    """Status einer Datenquelle inkl. Freshness (fuer Quellstatus-Anzeigen)."""

    source: str
    integration_kind: AdapterKind
    state: AdapterState
    api_version: str | None = None
    last_success_at: datetime | None = None
    last_error: str | None = Field(default=None, description="ohne Secrets/Stacktraces")
    checked_at: datetime


class ResourceAvailability(BaseModel):
    """Verfuegbarkeit einer inventarisierten Ressource (Host/VM/LXC/…)."""

    resource_type: ResourceType
    external_id: str
    name: str | None = None
    status: ResourceStatus
    checked_at: datetime
    detail: str | None = None


class ServiceAvailability(BaseModel):
    """Verfuegbarkeit eines Services (Monitoring-Target, Monitor, …)."""

    service: str
    status: ResourceStatus
    checked_at: datetime
    detail: str | None = None


class EventSeverity(StrEnum):
    """Vereinfachter Schweregrad (fachlich: info < warning < critical)."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    """Lebenzyklus-Zustand eines Alerts/Events."""

    ACTIVE = "active"
    RESOLVED = "resolved"
    UNKNOWN = "unknown"


class ResourceRef(BaseModel):
    """Ressourcen-Bezug eines Events (Referenz auf das Inventar-Identitets-Triple)."""

    resource_type: ResourceType
    external_id: str
    name: str | None = None


class NormalizedEvent(BaseModel):
    """Vereinigtes Event-Modell (normalisiert, dedup-faehig).

    ``fingerprint`` ist der stabile Dedup-Schluessel (siehe events.py).
    Kein eigener Persist-Store in R1 — das Modell ist der Contract fuer den
    vorgeschlagenen Event-Store (docs/proposals/agent4-monitoring-api.md).
    """

    fingerprint: str
    source: str
    source_event_id: str | None = None
    severity: EventSeverity
    event_type: str
    message: str
    status: AlertStatus = AlertStatus.UNKNOWN
    resource: ResourceRef | None = None
    occurred_at: datetime
    received_at: datetime
    extra: dict[str, Any] = Field(default_factory=dict)


class NormalizedAlert(BaseModel):
    """Vereinigtes Alert-Modell (z. B. aus Alertmanager/Uptime Kuma)."""

    fingerprint: str
    source: str
    source_alert_id: str | None = None
    severity: EventSeverity
    name: str
    summary: str | None = None
    status: AlertStatus = AlertStatus.ACTIVE
    resource: ResourceRef | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    started_at: datetime | None = None
    received_at: datetime


@runtime_checkable
class MonitoringBackend(Protocol):
    """Verbindliche Schnittstelle aller Monitoring-Backends (Agent 4, R1).

    Alle Methoden sind lesend, asynchron und muessen die Timeouts der
    Integration einhalten. Fehler werden als AdapterError-Hierarchie geworfen
    (stabile AdapterState-Werte).
    """

    name: str
    kind: AdapterKind

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus: ...

    async def capabilities(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> AdapterCapabilities: ...

    async def discover(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> AsyncIterator[ResourceRecord]: ...

    async def source_status(self, config: AdapterConfig, secrets: SecretsProvider) -> DataSourceStatus: ...

    async def current_metrics(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        resource_type: ResourceType,
        external_id: str,
    ) -> MetricsRecord: ...

    async def historical_metrics(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        metric: str,
        labels: dict[str, str],
        range: TimeRange,
    ) -> list[TimeSeries]: ...

    async def host_availability(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> list[ResourceAvailability]: ...

    async def service_availability(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> list[ServiceAvailability]: ...

    async def events(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> AsyncIterator[NormalizedEvent]: ...

    async def alerts(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> AsyncIterator[NormalizedAlert]: ...


class BaseMonitoringBackend(abc.ABC):
    """Basisklasse mit sicheren Defaults (analog BaseAdapter).

    Implementierungen uebernehmen ``verify``/``capabilities``/``discover``;
    alle übrigen Methoden haben Defaults (NOT_IMPLEMENTED bzw. leer), damit
    ein Backend ehrlich nur die Funktionen liefert, die es wirklich hat.
    """

    name: str
    kind: AdapterKind = AdapterKind.MONITORING

    @abc.abstractmethod
    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus: ...

    @abc.abstractmethod
    async def capabilities(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> AdapterCapabilities: ...

    @abc.abstractmethod
    async def discover(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> AsyncIterator[ResourceRecord]: ...

    async def health(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        """Leichte, wiederholbare Health-Pruefung (Default: verify)."""
        return await self.verify(config, secrets)

    async def source_status(self, config: AdapterConfig, secrets: SecretsProvider) -> DataSourceStatus:
        """Datenquellenstatus aus verify (Backends koennen feiner auflösen)."""
        checked_at = datetime.now(UTC)
        try:
            status = await self.verify(config, secrets)
        except AdapterError as exc:
            return DataSourceStatus(
                source=self.name,
                integration_kind=self.kind,
                state=exc.state,
                last_error=exc.message,
                checked_at=checked_at,
            )
        return DataSourceStatus(
            source=self.name,
            integration_kind=self.kind,
            state=status.state,
            api_version=status.api_version,
            last_success_at=status.checked_at if status.state is AdapterState.OK else None,
            last_error=None if status.state is AdapterState.OK else status.message,
            checked_at=checked_at,
        )

    async def current_metrics(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        resource_type: ResourceType,
        external_id: str,
    ) -> MetricsRecord:
        raise AdapterError(
            message=f"current_metrics() ist von Backend '{self.name}' nicht implementiert",
            state=AdapterState.NOT_IMPLEMENTED,
        )

    async def historical_metrics(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        metric: str,
        labels: dict[str, str],
        range: TimeRange,
    ) -> list[TimeSeries]:
        raise AdapterError(
            message=f"historical_metrics() ist von Backend '{self.name}' nicht implementiert",
            state=AdapterState.NOT_IMPLEMENTED,
        )

    async def host_availability(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> list[ResourceAvailability]:
        raise AdapterError(
            message=f"host_availability() ist von Backend '{self.name}' nicht implementiert",
            state=AdapterState.NOT_IMPLEMENTED,
        )

    async def service_availability(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> list[ServiceAvailability]:
        raise AdapterError(
            message=f"service_availability() ist von Backend '{self.name}' nicht implementiert",
            state=AdapterState.NOT_IMPLEMENTED,
        )

    async def events(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[NormalizedEvent]:
        """Keine Events — leerer Async-Iterator (Events sind optional).

        Das ``yield`` in der leeren Schleife macht die Funktion zu einem
        Async-Generator ohne Werte; Subclasses koennen so delegieren:
        ``async for event in super().events(...): yield event``.
        """
        for item in ():
            yield item

    async def alerts(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[NormalizedAlert]:
        """Keine Alerts — leerer Async-Iterator (Alerts sind optional)."""
        for item in ():
            yield item
