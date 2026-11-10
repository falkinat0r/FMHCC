"""Adapter-Interfaces (frozen, R0).

Jede Integration (Proxmox, TrueNAS, Pi-hole, Tailscale, Docker, Monitoring,
Home Assistant) implementiert das ``IntegrationAdapter``-Protokoll und wird
ueber ``app.integrations.registry`` registriert. Die UI und das REST-API
reden NIE direkt mit Adaptern — nur ueber diese gemeinsamen Interfaces und
die normalisierten Ressourcen-Contracts.
"""

from app.adapters.base import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterState,
    AdapterStatus,
    BaseAdapter,
    IntegrationAdapter,
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
    AdapterTimeoutError,
    AdapterUnreachableError,
    AdapterVersionError,
)

__all__ = [
    "AdapterApiError",
    "AdapterAuthError",
    "AdapterCapabilities",
    "AdapterConfig",
    "AdapterConfigError",
    "AdapterError",
    "AdapterState",
    "AdapterStatus",
    "AdapterTimeoutError",
    "AdapterUnreachableError",
    "AdapterVersionError",
    "BaseAdapter",
    "IntegrationAdapter",
    "MetricValue",
    "MetricsRecord",
    "ResourceRecord",
    "SecretsProvider",
]
