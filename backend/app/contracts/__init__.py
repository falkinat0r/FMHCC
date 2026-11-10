"""EINGEFRORENE API-Contracts (R0).

Dieses Paket ist die verbindliche Schnittstelle zwischen Backend-Modulen,
dem Frontend (generierter Client) und den Folge-Agenten. Aenderungen nur
ueber dokumentierte Vorschlaege in ``docs/proposals/`` — nie stillschweigend.

Stabile Praeprinzen:
- Versionierte Endpoints ``/api/v1/...``
- Einheitliche Error-Envelope (app.errors.ErrorEnvelope)
- UTC-Zeitstempel (datetime mit tz)
- Paging-Envelope (app.contracts.pagination.Paged)
- Zustandsmodelle: healthy/degraded/down/unknown/not_configured
"""

from app.contracts.audit import AuditEventOut
from app.contracts.auth import (
    BootstrapRequest,
    BootstrapResponse,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
)
from app.contracts.health import HealthCheck, HealthStatus, LiveHealthResponse, ReadyHealthResponse
from app.contracts.integrations import (
    IntegrationCreate,
    IntegrationOut,
    IntegrationUpdate,
    VerifyResponse,
    VerifyStatus,
)
from app.contracts.pagination import Paged
from app.contracts.resources import ResourceDetailOut, ResourceOut, ResourceRelationOut
from app.contracts.users import UserCreate, UserOut, UserUpdate
from app.contracts.version import VersionResponse

__all__ = [
    "AuditEventOut",
    "BootstrapRequest",
    "BootstrapResponse",
    "CurrentUserResponse",
    "HealthCheck",
    "HealthStatus",
    "IntegrationCreate",
    "IntegrationOut",
    "IntegrationUpdate",
    "LiveHealthResponse",
    "LoginRequest",
    "LoginResponse",
    "LogoutResponse",
    "Paged",
    "ReadyHealthResponse",
    "ResourceDetailOut",
    "ResourceOut",
    "ResourceRelationOut",
    "UserCreate",
    "UserOut",
    "UserUpdate",
    "VerifyResponse",
    "VerifyStatus",
    "VersionResponse",
]
