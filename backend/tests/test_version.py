"""Version-Endpoint-Test (R1).

Der Release-Marker ist auf R1 erhoeht (Agent 1 Backend-Core). Der Wert ist
kein eingefrorener Contract (VersionResponse.release ist ein freier String),
daher ist die Aenderung ohne Contract-Vorschlag legitim.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_version_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "hcc-api"
    assert body["release"] == "R1"
    assert body["commit"] == "test"  # aus Test-Settings
