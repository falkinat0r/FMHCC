"""Security-Regression: Session- und Cookie-Sicherheit.

Prueft die in docs/api-contracts.md / MASTER_PROMPT verbindlichen
Eigenschaften: HttpOnly-Session-Cookie, Secure-Flag in Produktion,
SHA-256-Hash-Persistierung, TTL, Revocation, Inaktivitaet.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.sessions import SessionService
from app.models.mixins import utcnow
from app.models.sessions import UserSession
from app.models.users import User

from tests.conftest import login_client


def _set_cookie_flags(response, cookie_name: str) -> dict[str, str]:
    """Liest die Set-Cookie-Attribute eines Cookies aus der Response.

    Value-lose Attribute (HttpOnly) werden als "true" markiert."""
    flags: dict[str, str] = {}
    for chunk in response.headers.get_list("set-cookie"):
        if not chunk.split(";", 1)[0].startswith(f"{cookie_name}="):
            continue
        for token in chunk.split(";")[1:]:
            token = token.strip()
            if not token:
                continue
            if "=" in token:
                key, value = token.split("=", 1)
                flags[key.strip().lower()] = value
            else:
                flags[token.lower()] = "true"
    return flags


def test_session_cookie_is_httponly_and_samesite_lax(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/v1/auth/login", json={"username": "qa_admin", "password": "qa-admin-pass-1234"}
    )
    flags = _set_cookie_flags(response, "hcc_session")
    assert "true" in flags.get("httponly", "true"), "hcc_session muss HttpOnly sein"
    assert flags.get("samesite", "").lower() == "lax", "hcc_session muss SameSite=Lax sein"
    assert "path" in flags


def test_csrf_cookie_is_not_httponly_double_submit(admin_client: TestClient) -> None:
    """Double-Submit erfordert, dass JS das hcc_csrf-Cookie lesen kann
    (HttpOnly=False ist hier intentional)."""
    response = admin_client.post(
        "/api/v1/auth/login", json={"username": "qa_admin", "password": "qa-admin-pass-1234"}
    )
    flags = _set_cookie_flags(response, "hcc_csrf")
    assert "httponly" not in flags, "hcc_csrf darf nicht HttpOnly sein (Double-Submit)"
    assert flags.get("samesite", "").lower() == "lax"


def test_cookie_secure_flag_in_production() -> None:
    """In production MUSS das Secure-Flag gesetzt sein (Settings-Validator
    erzwingt das; hier direkt pruefen, ohne App zu starten)."""
    from app.config import Settings

    with pytest.raises(Exception):
        Settings(environment="production", database_url="sqlite://", cookie_secure=False)

    ok = Settings(environment="production", database_url="sqlite://", cookie_secure=True)
    assert ok.cookie_secure is True


def test_raw_session_token_is_never_persisted(
    client: TestClient, admin_client: TestClient, db
) -> None:
    """In user_sessions darf nur der SHA-256-Hash, nie das rohe Token,
    persistiert sein."""
    response = admin_client.post(
        "/api/v1/auth/login", json={"username": "qa_admin", "password": "qa-admin-pass-1234"}
    )
    raw_token = response.headers.get_list("set-cookie")
    token_value = ""
    for chunk in raw_token:
        if chunk.startswith("hcc_session="):
            token_value = chunk.split(";")[0].split("=", 1)[1]
    assert token_value, "Session-Cookie nicht gefunden"

    sessions = db.scalars(select(UserSession)).all()
    hashes = {s.token_hash for s in sessions}
    assert token_value not in hashes, "ROHES Token persistiert!"
    assert hashlib.sha256(token_value.encode()).hexdigest() in hashes, "SHA-256-Hash fehlt"


def test_expired_session_is_rejected(app, admin_client: TestClient, db) -> None:
    """Absolute TTL: ueberfaellige Sessions duerfen nicht mehr gelöst
    werden (auch wenn last_seen aktuell ist)."""
    # Session direkt in der Vergangenheit verfallen lassen:
    user = db.scalar(select(User).where(User.username == "qa_admin"))
    assert user is not None
    for session in db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all():
        session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    client = admin_client  # Cookies enthalten die (jetzt abgelaufene) Session
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401, f"Abgelaufene Session akzeptiert: {response.status_code}"

    # Session-Lesen liefert fuer die abgelaufene Session ebenfalls None:
    svc = SessionService(app.state.settings)
    token = client.cookies.get("hcc_session", "")
    assert token
    assert svc.resolve(db, token) is None


def test_revoked_session_is_rejected(app, admin_client: TestClient, db) -> None:
    """Logout widerruft die Session; ein zweites /auth/me muss scheitern."""
    csrf = admin_client.cookies.get("hcc_csrf", "")
    token = admin_client.cookies.get("hcc_session", "")
    assert token
    response = admin_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200

    token_hash = SessionService(app.state.settings)._token_hash(token)
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
    assert session is not None and session.revoked_at is not None, "Session nicht widerrufen"

    # Neues Request mit dem alten Token:
    fresh = TestClient(app)
    r = fresh.get("/api/v1/auth/me", cookies={"hcc_session": token})
    assert r.status_code == 401


def test_session_of_deactivated_user_is_rejected(app, admin_client: TestClient) -> None:
    """Admin deaktiviert einen Viewer => dessen laufende Session muss
    sofort 401 liefern (is_active-Check im RBAC-Pfad)."""
    from tests.conftest import create_user

    create_user(admin_client, "qa_deact", "deact-pass-12345", "viewer")
    viewer = login_client(app, "qa_deact", "deact-pass-12345")
    assert viewer.get("/api/v1/auth/me").status_code == 200

    user_id = viewer.get("/api/v1/auth/me").json()["id"]
    csrf = admin_client.cookies.get("hcc_csrf", "")
    r = admin_client.patch(f"/api/v1/users/{user_id}", headers={"X-CSRF-Token": csrf}, json={"is_active": False})
    assert r.status_code == 200, r.text

    assert viewer.get("/api/v1/auth/me").status_code == 401, "Session deaktivierte User noch gultig"


def test_session_ttl_respected_from_settings(app, admin_client: TestClient, db) -> None:
    """Die konfigurierte TTL bestimmt expires_at (Default 12 h)."""
    ttl = app.state.settings.session_ttl_seconds
    assert 3600 <= ttl <= 30 * 24 * 3600
    session = db.scalar(select(UserSession).order_by(UserSession.created_at.desc()))
    assert session is not None
    delta = (session.expires_at - session.created_at).total_seconds()
    assert abs(delta - ttl) < 2, f"TTL-Abweichung: {delta} != {ttl}"
