"""Health-Readiness-Tests (R1): Migration-Status-Check.

Der Readiness-Endpunkt prueft bei PostgreSQL-Datenbanken, dass
``alembic_version`` existiert und dem Repository-Head entspricht.
In Tests (SQLite) bleibt das Verhalten unveraendert (kein Migration-Check).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

POSTGRES_URL = "postgresql+psycopg://hcc:hcc@127.0.0.1:5432/hcc"


def _as_postgres(client: TestClient) -> None:
    client.app.state.settings.database_url = POSTGRES_URL


def test_ready_on_sqlite_has_no_migration_check(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    names = {check["name"] for check in response.json()["checks"]}
    assert "database" in names
    assert "migration" not in names


def test_ready_postgres_migrated_is_ok(client: TestClient, db) -> None:
    db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
    db.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0001')"))
    db.commit()
    _as_postgres(client)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    migration = next(check for check in body["checks"] if check["name"] == "migration")
    assert migration["status"] == "ok"


def test_ready_postgres_out_of_sync_is_degraded(client: TestClient, db) -> None:
    db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
    db.execute(text("INSERT INTO alembic_version (version_num) VALUES ('9999')"))
    db.commit()
    _as_postgres(client)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    migration = next(check for check in body["checks"] if check["name"] == "migration")
    assert migration["status"] == "degraded"
    assert migration["message"]


def test_ready_postgres_unmigrated_is_degraded(client: TestClient) -> None:
    # alembic_version fehlt => Datenbank nicht migriert.
    _as_postgres(client)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    migration = next(check for check in body["checks"] if check["name"] == "migration")
    assert migration["status"] == "degraded"


def test_ready_postgres_database_down_still_unavailable(client: TestClient) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    original = client.app.state.session_factory

    def broken_factory():
        raise SQLAlchemyError("connection refused")

    client.app.state.session_factory = broken_factory
    _as_postgres(client)
    try:
        response = client.get("/api/v1/health/ready")
    finally:
        client.app.state.session_factory = original
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    # Datenbank-Check ist unavailable; Migration-Check wird bei DB-Down
    # nicht ausgefuehrt (keine separate Pruefung noetig).
    names = {check["name"] for check in body["checks"]}
    assert "database" in names
