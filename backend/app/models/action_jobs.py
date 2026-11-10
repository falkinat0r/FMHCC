"""Action-Jobs (idempotenzbewusste, auditierte Schreibanfuege; R1+) — Schema R0-frozen.

Noch kein Adapter darf diese Tabelle in R0 beschreiben; das Schema ist
eingefroren, damit Agent 3 (Proxmox) und QA gegen stabile Contracts testen
koennen. Jede Aktion erfordert RBAC (operator+), Bestaetigung und Audit.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, enum_values
from app.models.mixins import TimestampMixin


class ActionType(StrEnum):
    """Erlaubte VM/LXC-Aktionen (frozen; erzwungene Stops erst in spaeterem Release)."""

    START = "start"
    SHUTDOWN = "shutdown"  # sanfter Shutdown
    REBOOT = "reboot"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionJob(TimestampMixin, Base):
    __tablename__ = "action_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    # Enum(native_enum=False, create_constraint=True): VARCHAR + CHECK
    # (Namen ck_action_jobs_* ueber die Naming-Convention), liefert beim
    # Lesen echte Enum-Instanzen.
    action: Mapped[ActionType] = mapped_column(
        Enum(
            ActionType,
            name="action",
            native_enum=False,
            length=16,
            create_constraint=True,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    # RESTRICT (Default): Historie ueberlebt Integration-/User-Loeschung nicht
    # still — Aktion-Jobs bleiben referenzintakt.
    integration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integrations.id"), nullable=False, index=True
    )
    external_resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="status",
            native_enum=False,
            length=16,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=JobStatus.PENDING,
        nullable=False,
    )
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
