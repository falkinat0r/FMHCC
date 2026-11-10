"""Version-Endpoint-Test (R0)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_version_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "hcc-api"
    assert body["release"] == "R0"
    assert body["commit"] == "test"  # aus Test-Settings
