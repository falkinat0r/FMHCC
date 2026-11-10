"""Normalisiertes Ressourcen-Inventar (frozen Ressourcen-Contract, R0).

Eindeutige Identitaet: ``(integration_id, resource_type, external_id)``
(Resource-Key). Deduplizierung ueber ``app.inventory.base.upsert_resources``.
Zustandswerte sind fachlich getrennt — niemals zufaellige Erfolgswerte.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, enum_values
from app.models.mixins import TimestampMixin, utcnow


class ResourceType(StrEnum):
    """Ressourcen-Typen (frozen; Erweiterungen nur per Proposal)."""

    HOST = "host"                # physischer/Host-Maschine (Proxmox-Node, Docker-Host ...)
    NODE = "node"                # Cluster-Node
    VM = "vm"                    # QEMU-VM
    LXC = "lxc"                  # LXC-Container
    CONTAINER = "container"      # Docker-Container
    POOL = "pool"                # TrueNAS-Pool
    DATASET = "dataset"          # TrueNAS-Dataset
    TAILNET_NODE = "tailnet_node"
    DNS_STATS = "dns_stats"      # Pi-hole-Blocking-Statistik
    DASHBOARD = "dashboard"      # Monitoring-Dashboard/Quelle
    OTHER = "other"


class ResourceStatus(StrEnum):
    """Fachliche Zustaende (frozen) — exakt diese funf, nichts anderes."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"
    NOT_CONFIGURED = "not_configured"


class ResourceSource(StrEnum):
    """Herkunft/Evidenz (frozen)."""

    API = "api"
    MANUAL = "manual"
    INFERRED = "inferred"


class Resource(TimestampMixin, Base):
    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("integration_id", "resource_type", "external_id", name="resource_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    integration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Enum(native_enum=False, create_constraint=True): VARCHAR + CHECK
    # (Namen ck_resources_* ueber die Naming-Convention), liefert beim Lesen
    # echte Enum-Instanzen.
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(
            ResourceType,
            name="resource_type",
            native_enum=False,
            length=32,
            create_constraint=True,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[ResourceStatus] = mapped_column(
        Enum(
            ResourceStatus,
            name="status",
            native_enum=False,
            length=32,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=ResourceStatus.UNKNOWN,
        nullable=False,
    )
    source: Mapped[ResourceSource] = mapped_column(
        Enum(
            ResourceSource,
            name="source",
            native_enum=False,
            length=16,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=ResourceSource.API,
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def resource_key(self) -> tuple[str, str, str]:
        """Stabiler Dedup-Schlussel (Integration-ID, Typ, External-ID)."""
        return (str(self.integration_id), self.resource_type, self.external_id)


class ResourceRelation(Base):
    """Beziehungen zwischen Ressourcen, immer mit Evidenz (frozen)."""

    __tablename__ = "resource_relations"
    __table_args__ = (
        UniqueConstraint("source_resource_id", "target_resource_id", "relation_type", name="relation_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)  # runs_on | contains | connected_to | other
    evidence: Mapped[ResourceSource] = mapped_column(
        Enum(
            ResourceSource,
            name="evidence",
            native_enum=False,
            length=16,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=ResourceSource.API,
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=True)
