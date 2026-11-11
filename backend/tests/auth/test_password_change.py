"""Passwortwechsel-Tests (R1, Service-Ebene).

Der API-Endpunkt ist bewusst NICHT umgesetzt — der eingefrorene
R0-Contract kennt keinen solchen Pfad. Vorschlag:
``docs/proposals/backend-auth-change-password.md``. Der Service ist
vollstaendig testbereit und auditiert.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.auth.hashing import verify_password
from app.auth.sessions import SessionService
from app.errors import ApiError
from app.models.audit import AuditEvent
from app.models.sessions import UserSession
from app.models.users import Role, User
from app.users import service as user_service


def _user(db) -> User:
    return user_service.create_user(
        db,
        username="pwd-change",
        password="alt-passwort-123",
        role=Role.ADMIN,
    )


def test_change_password_updates_hash_and_clears_flag(db) -> None:
    user = _user(db)
    user_service.change_password(db, user, current_password="alt-passwort-123", new_password="neues-passwort-456")
    assert verify_password(user.password_hash, "neues-passwort-456") is True
    assert verify_password(user.password_hash, "alt-passwort-123") is False
    assert user.must_change_password is False


def test_change_password_wrong_current_password_is_rejected(db) -> None:
    user = _user(db)
    original_hash = user.password_hash
    with pytest.raises(ApiError) as exc:
        user_service.change_password(db, user, current_password="falsch-123456", new_password="neues-passwort-456")
    assert exc.value.status_code == 401
    assert user.password_hash == original_hash


def test_change_password_same_password_is_rejected(db) -> None:
    user = _user(db)
    with pytest.raises(ApiError) as exc:
        user_service.change_password(db, user, current_password="alt-passwort-123", new_password="alt-passwort-123")
    assert exc.value.status_code == 422


def test_change_password_revokes_all_sessions(db, settings) -> None:
    user = _user(db)
    service = SessionService(settings)
    created = service.create(db, user.id)
    db.flush()
    assert service.resolve(db, created.raw_token) is not None

    user_service.change_password(db, user, current_password="alt-passwort-123", new_password="neues-passwort-456")

    assert service.resolve(db, created.raw_token) is None
    row = db.scalar(select(UserSession).where(UserSession.user_id == user.id))
    assert row is not None and row.revoked_at is not None


def test_change_password_is_audited_without_secret_values(db) -> None:
    user = _user(db)
    user_service.change_password(db, user, current_password="alt-passwort-123", new_password="geheimstes-passwort-789")
    db.commit()
    events = db.scalars(select(AuditEvent).where(AuditEvent.action == "auth.password_changed")).all()
    assert len(events) == 1
    event = events[0]
    assert event.username == user.username
    rendered = str(event.details)
    assert "alt-passwort-123" not in rendered
    assert "geheimstes-passwort-789" not in rendered


def test_change_password_strength_validation(db) -> None:
    user = _user(db)
    with pytest.raises(ApiError) as exc:
        user_service.change_password(db, user, current_password="alt-passwort-123", new_password="zu_kurz")
    assert exc.value.status_code == 422
