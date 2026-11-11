"""Monitoring-Integration (Agent 4, R1).

Ein registrierter Adapter (kind='monitoring') mit Backends für vorhandene
Monitoring-Systeme: Prometheus (Metriken/Zeitreihen/Alerts), Grafana
(Health/Datenquellen), Loki (Quellenstatus/Labels), Uptime Kuma (Monitore).

Architekturentscheidung: Reuse vorhandener Instanzen — HCC setzt keine
Prometheus-/Grafana-/Loki-Installation voraus.
"""

from app.integrations.monitoring.base import (
    TIME_RANGE_SECONDS,
    TIME_RANGE_STEP_SECONDS,
    AlertStatus,
    BaseMonitoringBackend,
    DataSourceStatus,
    EventSeverity,
    MonitoringBackend,
    NormalizedAlert,
    NormalizedEvent,
    ResourceAvailability,
    ResourceRef,
    ServiceAvailability,
    TimeRange,
    TimeSeries,
    TimeSeriesPoint,
)
from app.integrations.monitoring.engine import MonitoringAdapter
from app.integrations.monitoring.events import EventDeduplicator, event_fingerprint, normalize_event
from app.integrations.monitoring.grafana import GrafanaBackend
from app.integrations.monitoring.loki import LokiBackend
from app.integrations.monitoring.prometheus import MetricTemplate, PrometheusBackend
from app.integrations.monitoring.uptime_kuma import UptimeKumaBackend

__all__ = [
    "AlertStatus",
    "BaseMonitoringBackend",
    "DataSourceStatus",
    "EventDeduplicator",
    "EventSeverity",
    "GrafanaBackend",
    "LokiBackend",
    "MetricTemplate",
    "MonitoringAdapter",
    "MonitoringBackend",
    "NormalizedAlert",
    "NormalizedEvent",
    "PrometheusBackend",
    "ResourceAvailability",
    "ResourceRef",
    "ServiceAvailability",
    "TimeRange",
    "TimeSeries",
    "TimeSeriesPoint",
    "TIME_RANGE_SECONDS",
    "TIME_RANGE_STEP_SECONDS",
    "UptimeKumaBackend",
    "event_fingerprint",
    "normalize_event",
]
