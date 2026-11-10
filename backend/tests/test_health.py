"""Health-/Readiness-Tests (R0)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_live_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "hcc-api"
    assert "time_utc" in body
    assert "Z" in body["time_utc"] or "+00:00" in body["time_utc"]


def test_ready_returns_ok_with_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert any(check["name"] == "database" and check["status"] == "ok" for check in body["checks"])


def test_ready_returns_503_when_database_unreachable(client: TestClient) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    original = client.app.state.session_factory

    def broken_factory():
        raise SQLAlchemyError("connection refused")

    client.app.state.session_factory = broken_factory
    try:
        response = client.get("/api/v1/health/ready")
    finally:
        client.app.state.session_factory = original
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"][0]["name"] == "database"
    assert body["checks"][0]["status"] == "unavailable"
