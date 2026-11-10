"""Integrationen (Anbindungen externer Systeme).

Secrets werden NICHT in der Datenbank gespeichert: ``secret_ref`` benennt
eine Referenz in der geschuetzten Secret-Datei (z. B. eine Env-Variable aus
/etc/hcc/secrets.env). Werte nur ueber den SecretsProvider loesen.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, enum_values
from app.models.mixins import TimestampMixin


class AdapterKind(StrEnum):
    """Typ der Anbindung (frozen Enum)."""

    PROXMOX = "proxmox"
    TRUENAS = "truenas"
    PIHOLE = "pihole"
    TAILSCALE = "tailscale"
    DOCKER = "docker"
    MONITORING = "monitoring"
    HOMEASSISTANT = "homeassistant"
    UNKNOWN = "unknown"


class IntegrationStatus(StrEnum):
    """Fachliche Zustandstrennung (frozen): niemals Zufallswerte."""

    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    ERROR = "error"
    DISABLED = "disabled"


class Integration(TimestampMixin, Base):
    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    integration_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Enum(native_enum=False, create_constraint=True): VARCHAR + CHECK
    # (Namen ck_integrations_* ueber die Naming-Convention), liefert beim
    # Lesen echte Enum-Instanzen.
    adapter: Mapped[AdapterKind] = mapped_column(
        Enum(
            AdapterKind,
            name="adapter",
            native_enum=False,
            length=32,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=AdapterKind.UNKNOWN,
        nullable=False,
    )
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(
            IntegrationStatus,
            name="status",
            native_enum=False,
            length=32,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=IntegrationStatus.NOT_CONFIGURED,
        nullable=False,
    )
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
