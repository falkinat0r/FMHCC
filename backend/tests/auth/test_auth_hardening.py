"""Auth-Hardening-Tests (R1).

- Bootstrap-Rate-Limit (oeffentlicher Endpoint)
- persistente Audit-Events auf Fehler-Pfaeden (Login/Bootstrap) — die
  Request-Session rollt bei Exceptions zurueck, Fehler-Audits muessen
  trotzdem ueberleben (record_audit(..., commit=True))
- Login-Timing-Gleichbehandlung (unbekannter User)
- Session-Purge und revoke_all_for_user
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.sessions import SessionService
from app.models.audit import AuditEvent
from app.models.sessions import UserSession
from app.models.users import Role, User
from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, TEST_BOOTSTRAP_TOKEN


def test_bootstrap_is_rate_limited_per_ip(client: TestClient) -> None:
    # 5 Versuche erlaubt, 6. => 429
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/bootstrap",
            json={"username": "x-user", "password": "falsches-passwort-1", "token": "falsches-token-0123456789abcdef"},
        )
        assert response.status_code == 401, response.text
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "x-user", "password": "falsches-passwort-1", "token": "falsches-token-0123456789abcdef"},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.headers.get("Retry-After") == "60"


def test_bootstrap_failure_is_audited_and_persisted(client: TestClient, db) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "x-user", "password": "falsches-passwort-1", "token": "falsches-token-0123456789abcdef"},
    )
    assert response.status_code == 401
    events = db.scalars(select(AuditEvent).where(AuditEvent.action == "auth.bootstrap.failed")).all()
    assert len(events) == 1
    assert events[0].details["reason"] == "unauthenticated"


def test_login_failure_for_unknown_user_is_audited_and_persisted(client: TestClient, db) -> None:
    client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    response = client.post("/api/v1/auth/login", json={"username": "niemand-da", "password": "irgendein-passwort-9"})
    assert response.status_code == 401
    # Auch ohne existierenden User wird (zeitlich) Argon2 verifiziert —
    # und das Fehlversuch wird persistiert, obwohl der Request rollt.
    events = db.scalars(select(AuditEvent).where(AuditEvent.action == "auth.login.failed")).all()
    assert len(events) == 1
    assert events[0].username is None


def test_login_failure_for_known_user_is_audited(client: TestClient, db) -> None:
    client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": "falsches-passwort-9"})
    assert response.status_code == 401
    events = db.scalars(select(AuditEvent).where(AuditEvent.action == "auth.login.failed")).all()
    assert len(events) == 1
    assert events[0].username == ADMIN_USERNAME


def test_revoke_all_for_user_invalidates_existing_sessions(client: TestClient, db, settings) -> None:
    client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    user = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert user is not None
    service = SessionService(settings)
    created = service.create(db, user.id)
    db.flush()
    assert service.resolve(db, created.raw_token) is not None

    revoked = service.revoke_all_for_user(db, user.id)
    assert revoked >= 1
    assert service.resolve(db, created.raw_token) is None


def test_purge_expired_removes_expired_and_revoked_sessions(client: TestClient, db, settings) -> None:
    client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    user = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert user is not None
    service = SessionService(settings)
    created = service.create(db, user.id)
    row = db.scalar(select(UserSession).where(UserSession.token_hash == service._token_hash(created.raw_token)))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    removed = service.purge_expired(db)
    assert removed >= 1
    assert db.scalar(select(UserSession).where(UserSession.id == row.id)) is None


def test_inactive_user_with_existing_session_cannot_act(client: TestClient, db, settings) -> None:
    client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    # Zweiten (aktiven) User als Viewer anlegen, dann deaktivieren.
    from app.users import service as user_service

    viewer = user_service.create_user(
        db, username="deactivate-me", password="deactivate-pass-123", role=Role.VIEWER
    )
    db.commit()
    # Session fuer den Viewer erzeugen
    service = SessionService(settings)
    created = service.create(db, viewer.id)
    db.commit()

    viewer.is_active = False
    db.commit()

    response = client.get("/api/v1/auth/me", cookies={"hcc_session": created.raw_token})
    assert response.status_code == 401


def test_session_limiter_and_bootstrap_limiter_are_independent(client: TestClient) -> None:
    # Login-Limit (10) und Bootstrap-Limit (5) greifen getrennt.
    # Erst Admin anlegen (Bootstrap-Call #1).
    assert client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    ).status_code == 201
    # Dann das Bootstrap-Limit volltreiben. Da jetzt ein User existiert,
    # antwortet der Endpoint 403 (nicht mehr verfuegbar) — aber JEDER Aufruf
    # veraehrt eine Limit-Position (Limit wird vor der Logik geprueft).
    # Calls #2-#5 => 403, Call #6 => 429 (rate-limited).
    for _ in range(4):
        assert client.post(
            "/api/v1/auth/bootstrap",
            json={"username": "x-user", "password": "falsches-passwort-1", "token": "falsches-token-0123456789abcdef"},
        ).status_code == 403
    assert client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "x-user", "password": "falsches-passwort-1", "token": "falsches-token-0123456789abcdef"},
    ).status_code == 429
    # Login-Limiter ist davon unberuehrt: Admin-Login moeglich.
    response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert response.status_code == 200
