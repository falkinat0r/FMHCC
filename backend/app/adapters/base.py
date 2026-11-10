"""Adapter-Protokoll und gemeinsame Typen (frozen, R0).

Vertragliche Praeprinzen:
- Adapter sind unabhaengig und abschaltbar; eine nicht erreichbare
  Integration darf das HCC nicht blockieren.
- Alle Methoden sind asynchron und muessen Timeouts einhalten
  (AdapterConfig.timeout_seconds).
- Secrets werden nur als Referenz (secret_ref) uebergeben und via
  SecretsProvider geloest — nie als Klartext in Konfiguration/DB.
- Zustandsbeobachtungen sind UTC; fehlende Daten => 'unknown'/'not_configured'.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.models.integrations import AdapterKind
from app.models.resources import ResourceStatus, ResourceType


class AdapterConfig(BaseModel):
    """Eingefrorene Adapter-Konfiguration (ohne Secret-Werte)."""

    base_url: str | None = None
    secret_ref: str | None = None
    timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    extra: dict[str, str] = Field(default_factory=dict)


class AdapterState(StrEnum):
    """Adapter-Zustand (frozen Enum-Werte)."""

    OK = "ok"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    API_ERROR = "api_error"
    VERSION_UNSUPPORTED = "version_unsupported"
    NOT_CONFIGURED = "not_configured"
    NOT_IMPLEMENTED = "not_implemented"


class AdapterStatus(BaseModel):
    state: AdapterState
    message: str | None = None
    api_version: str | None = None
    checked_at: datetime


class AdapterCapabilities(BaseModel):
    features: list[str] = Field(default_factory=list, description="z. B. ['discover', 'health', 'metrics']")
    api_version: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ResourceRecord(BaseModel):
    """Normalisiertes Discover-Ergebnis; Basis der Inventar-Deduplizierung."""

    resource_type: ResourceType
    external_id: str
    name: str | None = None
    status: ResourceStatus = ResourceStatus.UNKNOWN
    payload: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime
    parent_external_id: str | None = None
    parent_resource_type: ResourceType | None = None
    relation_type: str = "runs_on"


class MetricValue(BaseModel):
    value: float
    unit: str | None = None


class MetricsRecord(BaseModel):
    """Ergebnis von ``collect`` (Metriken immer mit Einheit, falls bekannt)."""

    external_id: str
    resource_type: ResourceType
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    collected_at: datetime


class SecretsProvider(Protocol):
    """Loest Secret-Referenzen zur Laufzeit (frozen)."""

    def get(self, name: str) -> str | None:  # pragma: no cover
        ...


@runtime_checkable
class IntegrationAdapter(Protocol):
    """Verbindliches Protokoll aller Adapter (frozen, R0)."""

    kind: AdapterKind

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        """Verbindung + Credentials pruefen (nur lesende Requests)."""
        ...

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        """Versions-/Fuehigkeitsmatrix der konkreten Instanz."""
        ...

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        """Ressourcen-Entdeckung (nur lesende Requests)."""
        ...

    async def health(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        """Leichte, wiederholbare Health-Pruefung."""
        ...

    async def collect(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        resource_type: ResourceType,
        external_id: str,
    ) -> MetricsRecord:
        """Metriken einer einzelnen Ressource (lesend)."""
        ...

    async def act(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        action: str,
        external_id: str,
        confirmed: bool,
    ) -> AdapterStatus:
        """Schreibaktion (R1+: operator+ RBAC, Bestaetigung, Audit erforderlich).

        ``confirmed=False`` muss mit Fehler antworten (kein versehentliches
        Ausfuehren). R0-Standard: not_implemented.
        """
        ...


class BaseAdapter(abc.ABC):
    """Bequeme Basisklasse: implementiert Defaults und Fehler-Helfer.

    Folge-Agenten (Proxmox, Monitoring, ...) erben von dieser Klasse und
    implementieren die abstrakten Methoden; ``health``/``collect``/``act``
    haben sichere Defaults.
    """

    kind: AdapterKind

    @abc.abstractmethod
    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus: ...

    @abc.abstractmethod
    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities: ...

    @abc.abstractmethod
    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]: ...

    async def health(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        return await self.verify(config, secrets)

    async def collect(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        resource_type: ResourceType,
        external_id: str,
    ) -> MetricsRecord:
        from app.adapters.errors import AdapterError

        raise AdapterError(
            message="collect() ist von diesem Adapter nicht implementiert",
            state=AdapterState.NOT_IMPLEMENTED,
        )

    async def act(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        action: str,
        external_id: str,
        confirmed: bool,
    ) -> AdapterStatus:
        from app.adapters.errors import AdapterError

        if not confirmed:
            raise AdapterError(
                message="Bestaetigung fehlt fuer Schreibaktion",
                state=AdapterState.NOT_CONFIGURED,
            )
        raise AdapterError(
            message=f"Aktion '{action}' ist nicht implementiert",
            state=AdapterState.NOT_IMPLEMENTED,
        )
