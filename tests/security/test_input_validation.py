"""Security-Regression: Input-Validierung, Injection- und Traversal-Versuche.

Ziel: Nachweisen, dass maessige/malformed Eingaben immer kontrollierte
4xx-Error-Envelopes liefern und nie 500s, Stacktraces oder
Datei-/System-Zugriff ausloesen.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/integrations/..",
        "/api/v1/integrations/..%2F..%2Fetc%2Fpasswd",
        "/api/v1/integrations/%00",
        "/api/v1/integrations/a" * 200,
    ],
)
def test_path_traversal_attempts_are_404_or_422(client: TestClient, path: str) -> None:
    """Kein 200, keine 500, kein Traceback. 401 ist gueltig, weil die
    geschuetzten Endpunkte ohne Session zuerst die Auth-Schicht treffen."""
    response = client.get(path)
    assert response.status_code in (400, 401, 404, 422), f"{path}: {response.status_code}"
    assert "Traceback" not in response.text


@pytest.mark.parametrize(
    "integration_id",
    [
        "UPPER-CASE",  # Pattern verletzen (Großbuchstaben)
        "-leading-dash",
        "has underscore",
        "x" * 65,  # > 64 Zeichen
        "valid-id'; DROP TABLE integrations;--",
        "id' OR '1'='1",
    ],
)
def test_integration_slug_validation_blocks_injection(
    client: TestClient, admin_client: TestClient, integration_id: str
) -> None:
    """Schreibversuche mit maessigen Slugs werden per 422 abgefangen;
    Leseversuche werden 404 — die Tabellen bleiben intakt."""
    csrf = admin_client.cookies.get("hcc_csrf", "")
    put = admin_client.put(
        f"/api/v1/integrations/{integration_id}",
        headers={"X-CSRF-Token": csrf},
        json={
            "integration_id": integration_id,
            "name": "n",
            "adapter": "unknown",
            "base_url": None,
            "secret_ref": None,
        },
    )
    assert put.status_code in (404, 422, 400), f"PUT {integration_id}: {put.status_code}"
    assert "Traceback" not in put.text

    get = admin_client.get(f"/api/v1/integrations/{integration_id}")
    assert get.status_code in (404, 422, 400)
    assert "Traceback" not in get.text


def test_sql_injection_in_query_filters_is_harmless(app, admin_client: TestClient) -> None:
    """LIKE-Filter sind parameterisiert; Wild-/Injection-Versuche liefern
    kontrollierte (leere) Ergebnisse, nie 500."""
    viewer_payload = {"username": "qa_fuzz", "password": "fuzz-pass-12345", "role": "viewer"}
    csrf = admin_client.cookies.get("hcc_csrf", "")
    admin_client.post("/api/v1/users", headers={"X-CSRF-Token": csrf}, json=viewer_payload)
    from tests.conftest import login_client

    viewer = login_client(app, "qa_fuzz", "fuzz-pass-12345")
    for q in ("1; DROP TABLE resources;--", "' OR '1'='1", "%", "_", "abc%def"):
        response = viewer.get("/api/v1/resources", params={"q": q})
        assert response.status_code == 200, f"q={q!r}: {response.status_code}"
    # Tabellen existieren weiterhin:
    assert viewer.get("/api/v1/resources").status_code == 200


@pytest.mark.parametrize(
    "username",
    [
        "UPPER",  # Uppercase erlaubt? Nein: Pattern ^[a-z0-9][a-z0-9._-]*$
        "a" * 65,
        "-lead",
        "ok user",
        "user<script>",
        "user\ninjection",
    ],
)
def test_username_injection_is_rejected(admin_client: TestClient, username: str) -> None:
    csrf = admin_client.cookies.get("hcc_csrf", "")
    response = admin_client.post(
        "/api/v1/users",
        headers={"X-CSRF-Token": csrf},
        json={"username": username, "password": "passw0rt-12345", "role": "viewer"},
    )
    assert response.status_code in (400, 422), f"username={username!r}: {response.status_code}"


def test_malformed_uuid_is_422_envelope(admin_client: TestClient) -> None:
    """Authentifizierter Request: der Pfad-Parameter wird validiert
    (422). Unauthentifiziert greift zuerst die Auth-Schicht (401)."""
    response = admin_client.get("/api/v1/resources/not-a-uuid")
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"] is not None


def test_oversized_parameters_rejected(admin_client: TestClient) -> None:
    # page_size > 200 => 422 (Admin hat resources.read)
    response = admin_client.get("/api/v1/resources", params={"page_size": 201})
    assert response.status_code == 422

    # name > 128 => 422
    csrf = admin_client.cookies.get("hcc_csrf", "")
    response = admin_client.put(
        "/api/v1/integrations/qa-big",
        headers={"X-CSRF-Token": csrf},
        json={"integration_id": "qa-big", "name": "x" * 200, "adapter": "unknown"},
    )
    assert response.status_code == 422


def test_non_json_body_is_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        content=b"\x00\x01\x02 binary-garbage",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 422
    assert "Traceback" not in response.text


def test_method_not_allowed_returns_envelope(client: TestClient) -> None:
    """405 muss die Envelope-Form haben (Code-Detail siehe
    security-findings: Dokument nennt method_not_allowed, Code liefert
    aktuell not_found — der Contract-Shape-Test gilt hier)."""
    response = client.get("/api/v1/auth/logout")
    assert response.status_code == 405
    body = response.json()
    assert "error" in body and set(body["error"].keys()) == {"code", "message", "details", "request_id"}
