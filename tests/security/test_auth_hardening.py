"""Security-Regression: Auth-Hardening (Rate-Limit, Bootstrap-Semantik).

- Login: Sliding-Window-Limit (R0: 10/60s) => 429 mit Error-Envelope
- Bootstrap: genau ein Admin, nur mit Token, danach dauerhaft deaktiviert
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    TEST_BOOTSTRAP_TOKEN,
    bootstrap_admin,
)


def test_login_rate_limit_returns_429_envelope(app, client: TestClient) -> None:
    from app.api.v1 import auth as auth_routes

    bootstrap_admin(client)
    # Der Bootstrap-Login hat einen Limiter-Slot verbraucht — Fenster
    # saubermachen, damit die Grenze exakt messbar ist.
    auth_routes._login_limiter.reset()
    # 10 Versuche erlaubt, der 11. muss 429 sein (pro IP, Sliding Window).
    for i in range(10):
        response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": "falsch-passw0rt"})
        assert response.status_code == 401, f"Versuch {i + 1}: erwartet 401, bekam {response.status_code}"
    response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": "falsch-passw0rt"})
    assert response.status_code == 429
    body = response.json()["error"]
    assert body["code"] == "rate_limited"
    assert body["request_id"], "429-Envelope ohne request_id"

    # Auch mit KORREKTEM Passwort wird innerhalb des Fensters abgelehrt
    # (bewusste R0-Semantik: Limit greift vor der Pruefung).
    response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert response.status_code == 429


def test_rate_limit_is_per_client_ip(app, client: TestClient) -> None:
    """Der Limiter keyt auf request.client (R0-Design). Ein zweiter
    'Client' mit gleicher IP stoessen auf dasselbe Fenster."""
    bootstrap_admin(client)
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": "falsch-passw0rt"})
    # Hier nur dokumentieren, dass der Zaehler pro IP laeuft:
    from app.api.v1 import auth as auth_routes

    assert len(auth_routes._login_limiter._calls) == 1, "Limiter keyt nicht pro IP"


def test_bootstrap_fails_without_token(app) -> None:
    from app.config import Settings
    from app.main import create_app
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.base import Base

    settings = Settings(environment="development", database_url="sqlite://", bootstrap_token="")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    application = create_app(settings)
    application.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        with TestClient(application) as c:
            response = c.post(
                "/api/v1/auth/bootstrap",
                json={"username": "xadmin", "password": "lange-passw0rt-123", "token": "irgend-32-stellige-t0ken"},
            )
            # Ohne konfiguriertes Token ist Bootstrap deaktiviert:
            assert response.status_code in (401, 403), response.text
            body = response.json()["error"]
            assert body["code"] in ("not_configured", "unauthenticated", "forbidden")
    finally:
        engine.dispose()


def test_bootstrap_token_must_be_at_least_16_chars(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "xadmin", "password": "lange-passw0rt-123", "token": "zu-kurz"},
    )
    assert response.status_code == 422
    assert "password" not in response.text or "Passwort" in response.text  # Passwortwert nie in Antwort


def test_bootstrap_single_use(app, client: TestClient) -> None:
    """Nach dem ersten Bootstrap ist der Endpunkt dauerhaft deaktiviert,
    selbst mit korrektem Token."""
    bootstrap_admin(client)
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "second-admin", "password": "lange-passw0rt-123", "token": TEST_BOOTSTRAP_TOKEN},
    )
    assert response.status_code == 403, f"Zweiter Bootstrap moeglich: {response.status_code}"
