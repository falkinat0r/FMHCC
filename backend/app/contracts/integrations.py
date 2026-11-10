"""Integrations-Contract (frozen, R0).

Secrets: Die Datenbank speichert nur ``secret_ref`` (Referenzname), keine
Werte. Werte werden zur Laufzeit durch den SecretsProvider (geschuetzte
Secret-Datei) geloest und nie in API-Antworten, Logs oder Audit-Details
mitgegeben.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, Field

from app.models.integrations import AdapterKind


class IntegrationCreate(BaseModel):
    integration_id: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
        description="Stabiler, eindeutiger Bezeichner (z. B. 'proxmox-1')",
    )
    name: str = Field(min_length=1, max_length=128)
    adapter: AdapterKind
    base_url: AnyHttpUrl | None = None
    secret_ref: str | None = Field(
        default=None,
        max_length=128,
        pattern=r"^[A-Za-z][A-Za-z0-9_]{0,127}$",
        description="Name der Secret-Umgebungsvariable (Wert bleibt in secrets.env)",
    )


class IntegrationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: AnyHttpUrl | None = None
    secret_ref: str | None = Field(
        default=None,
        max_length=128,
        pattern=r"^[A-Za-z][A-Za-z0-9_]{0,127}$",
    )
    disabled: bool | None = Field(
        default=None,
        description="true => Status 'disabled'; false => zurueck auf 'configured'",
    )


class IntegrationOut(BaseModel):
    id: uuid.UUID
    integration_id: str
    name: str
    adapter: AdapterKind
    status: str  # not_configured | configured | error | disabled
    capabilities: dict[str, Any]
    base_url: str | None = None
    secret_ref: str | None = None
    last_verified_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class VerifyStatus(StrEnum):
    """Adapter-Zustand in API-Antworten (frozen)."""

    OK = "ok"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    API_ERROR = "api_error"
    VERSION_UNSUPPORTED = "version_unsupported"
    NOT_CONFIGURED = "not_configured"
    NOT_IMPLEMENTED = "not_implemented"


class VerifyResponse(BaseModel):
    integration_id: str
    status: VerifyStatus
    message: str | None = None
    capabilities: dict[str, Any] = {}
    api_version: str | None = None
    checked_at: datetime
