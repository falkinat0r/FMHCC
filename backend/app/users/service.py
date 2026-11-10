"""User-Management (Eigentuemer ab R1: Agent 1 backend-auth; R0-Basis eingefroren).

Domänenlogik: Erstellung, Aenderungen, Last-Admin-Guard.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.log import record_audit
from app.auth.hashing import hash_password, verify_password
from app.errors import ErrorCode, http_error
from app.models.users import Role, User

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def validate_username(username: str) -> None:
    if not _USERNAME_RE.match(username) or not (3 <= len(username) <= 64):
        raise http_error(422, ErrorCode.VALIDATION_ERROR, "Username ist ungültig (3-64 Zeichen, a-z 0-9 . _ -)")


def validate_password(password: str) -> None:
    if not (10 <= len(password) <= 200):
        raise http_error(422, ErrorCode.VALIDATION_ERROR, "Passwort muss 10-200 Zeichen haben")


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def create_user(
    db: Session,
    *,
    username: str,
    password: str,
    role: Role = Role.VIEWER,
    display_name: str | None = None,
) -> User:
    validate_username(username)
    validate_password(password)
    if get_user_by_username(db, username) is not None:
        raise http_error(409, ErrorCode.CONFLICT, "Username ist bereits vergeben")
    user = User(
        username=username,
        display_name=display_name,
        role=role,
        password_hash=hash_password(password),
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    return user


def update_user(db: Session, user: User, *, role: Role | None = None, is_active: bool | None = None, display_name: str | None = None) -> User:
    """Aendert Rollen/Status mit Last-Admin-Guard.

    Regel: Der letzte aktive Admin darf nicht deaktiviert oder
    heruntergestuft werden — das System muss immer adminverwaltbar bleiben.
    """
    loses_admin_privilege = (role is not None and role != Role.ADMIN) or (is_active is False)
    if user.role == Role.ADMIN and loses_admin_privilege:
        active_admins = db.scalar(
            select(func.count()).select_from(User).where(User.role == Role.ADMIN, User.is_active.is_(True))
        )
        if active_admins <= 1:
            raise http_error(409, ErrorCode.CONFLICT, "Der letzte aktive Admin darf nicht demotiert oder deaktiviert werden")

    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if display_name is not None:
        user.display_name = display_name
    db.flush()
    return user


def count_active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == Role.ADMIN, User.is_active.is_(True))) or 0


def change_password(
    db: Session,
    user: User,
    *,
    current_password: str,
    new_password: str,
) -> None:
    """Aendert das Passwort eines Users (serverseitig, R1).

    Regeln:
    - Aktuelles Passwort muss verifiziert werden (konstanter Zeitabgleich
      ueber Argon2id; fehlgeschlagene Pruefung => 401).
    - Neues Passwort nach denselben Regeln wie bei der Erzeugung (10-200).
    - ``must_change_password`` wird zurueckgesetzt.
    - ALLE bestehenden Sessions des Users werden widerrufen (alle
      bisher ausgegebenen Cookies verlieren ihre Gueltigkeit sofort).
    - Wird auditiert (ohne Passwortwerte).
    """
    if not verify_password(user.password_hash, current_password):
        raise http_error(401, ErrorCode.UNAUTHENTICATED, "Aktuelles Passwort ist falsch")
    validate_password(new_password)
    if current_password == new_password:
        raise http_error(422, ErrorCode.VALIDATION_ERROR, "Neues Passwort muss sich vom aktuellen unterscheiden")

    user.password_hash = hash_password(new_password)
    user.must_change_password = False

    from app.auth.sessions import SessionService
    from app.config import Settings

    # Session-Verwaltung ohne Cookie-Einstellungen => neutrale Settings.
    service = SessionService(Settings(database_url="sqlite://"))
    revoked = service.revoke_all_for_user(db, user.id)

    record_audit(
        db,
        user=user,
        action="auth.password_changed",
        resource_type="user",
        resource_id=user.username,
        details={"sessions_revoked": revoked},
    )
    db.flush()


def list_users(db: Session, *, page: int, page_size: int) -> tuple[list[User], int]:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    users = db.scalars(
        select(User).order_by(User.username).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(users), total


def get_user(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)
