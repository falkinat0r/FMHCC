"""RBAC: Rollen, Berechtigungen, zentraler Pruefer (frozen, R0).

Rollen: viewer < operator < admin.
Berechtigungspruefung immer serverseitig, pro Endpunkt ueber
``require_permission`` — die UI darf niemals allein entscheiden.
"""

from __future__ import annotations

from fastapi import Request

from app.errors import ErrorCode, http_error
from app.models.users import Role

ROLE_LEVELS: dict[Role, int] = {
    Role.VIEWER: 1,
    Role.OPERATOR: 2,
    Role.ADMIN: 3,
}

# Stabile Berechtigungs-Keys (frozen). Neue Keys nur per Proposal.
PERMISSIONS: dict[str, Role] = {
    "resources.read": Role.VIEWER,
    "integrations.read": Role.VIEWER,
    "integrations.manage": Role.ADMIN,
    "actions.run": Role.OPERATOR,
    "users.manage": Role.ADMIN,
    "audit.read": Role.ADMIN,
    "settings.manage": Role.ADMIN,
}


def has_permission(role: Role, permission: str) -> bool:
    required = PERMISSIONS.get(permission)
    if required is None:
        return False
    return ROLE_LEVELS[role] >= ROLE_LEVELS[required]


def require_permission(permission: str):
    """FastAPI-Dependency-Fabrik: erzwingt Authentifizierung + Berechtigung.

    Nutzung: ``user: User = Depends(require_permission("actions.run"))``
    """

    # Hinweis: keine Return-Annotierung — FastAPI validiert sie als
    # Response-Field, und das ORM-Modell ist kein Pydantic-Modell.
    def _check(request: Request):
        user = getattr(request.state, "current_user", None)
        if user is None or not user.is_active:
            raise http_error(401, ErrorCode.UNAUTHENTICATED, "Anmeldung erforderlich")
        if not has_permission(user.role, permission):
            raise http_error(403, ErrorCode.FORBIDDEN, f"Berechtigung fehlend: {permission}")
        return user

    return _check
