"""Einmaliger Admin-Bootstrap (frozen Semantik, R0).

Bedingungen (alle erforderlich):
1. Es existieren NOCH KEINE User in der Datenbank.
2. ``HCC_BOOTSTRAP_TOKEN`` ist gesetzt und matcht (konstanter Zeitabgleich).
Der erstellte Admin hat ``must_change_password=True``. Danach ist der
Bootstrap-Endpoint dauerhaft deaktiviert (403) — es gibt kein zweites
Secret zurueck ins System.
"""

from __future__ import annotations

import hmac
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ErrorCode, http_error
from app.models.users import Role, User

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def bootstrap_available(db: Session) -> bool:
    return db.scalar(select(func.count()).select_from(User)) == 0


def create_bootstrap_admin(
    db: Session,
    settings: Settings,
    *,
    username: str,
    password: str,
    token: str,
) -> User:
    if not bootstrap_available(db):
        raise http_error(403, ErrorCode.FORBIDDEN, "Bootstrap ist nicht mehr verfuegbar (User existieren bereits)")
    if not settings.bootstrap_token:
        raise http_error(403, ErrorCode.NOT_CONFIGURED, "Bootstrap-Token ist nicht konfiguriert")
    if not hmac.compare_digest(token, settings.bootstrap_token):
        raise http_error(401, ErrorCode.UNAUTHENTICATED, "Bootstrap-Token ist ungültig")
    if not _USERNAME_RE.match(username) or len(username) < 3 or len(username) > 64:
        raise http_error(422, ErrorCode.VALIDATION_ERROR, "Username ist ungültig")
    if len(password) < 10 or len(password) > 200:
        raise http_error(422, ErrorCode.VALIDATION_ERROR, "Passwort muss 10-200 Zeichen haben")

    from app.auth.hashing import hash_password

    user = User(
        username=username,
        display_name=username.title(),
        role=Role.ADMIN,
        password_hash=hash_password(password),
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    return user
