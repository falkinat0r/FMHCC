"""Gemeinsame Mappings (Zeitstempel)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    """Immer timezone-aware UTC (Contract: UTC-Zeitstempel)."""
    return datetime.now(UTC)


class TimestampMixin:
    """created_at/updated_at fuer alle zentralementabenen Tabellen."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
