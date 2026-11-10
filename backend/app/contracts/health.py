"""Health-/Readiness-Contract (frozen)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class HealthCheck(BaseModel):
    name: str
    status: HealthStatus
    message: str | None = None
    duration_ms: float = Field(default=0.0, ge=0)


class LiveHealthResponse(BaseModel):
    """Live-Check: Process laeuft (systemd). Immer 200, wenn API antwortet."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    time_utc: datetime


class ReadyHealthResponse(BaseModel):
    """Readiness: API + Datenbank bereit. 503, wenn status != ok."""

    status: HealthStatus
    checks: list[HealthCheck]
    time_utc: datetime
