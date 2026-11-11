"""Error-Handling-Tests (R1): Rate-Limit-Header und 405-Verhalten.

- 429-Antworten tragen ``Retry-After`` (fuer Clients/Proxies nuerzlich).
- 405 wird weiterhin als Fehler-Envelope beantwortet. HINWEIS: Der
  maschinelle Code lautet in R0 'not_found' (frozen Mapping in
  app/errors.py). Die Doku (docs/api-contracts.md) nennt 'method_not_allowed'
  als vorgesehenen Code — die Code-Ergaenzung erfordert eine Aenderung am
  eingefrorenen ErrorCode-Enum und ist als Vorschlag dokumentiert:
  docs/proposals/backend-errors-method-not-allowed.md
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, TEST_BOOTSTRAP_TOKEN, csrf_headers


def test_login_rate_limited_includes_retry_after(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    for _ in range(10):
        assert client.post(
            "/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": "falsches-passwort-9"}
        ).status_code == 401
    response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": "falsches-passwort-9"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.headers.get("Retry-After") == "60"


def test_405_uses_error_envelope(client: TestClient) -> None:
    # State-aendernde Methode auf einen GET-Only-Pfad => 405 mit Envelope
    # (R0-frozen Mapping). Authentifiziert + mit CSRF, damit die
    # CSRF-Middleware nicht vorab 403 antwortet.
    client.post(
        "/api/v1/auth/bootstrap",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "token": TEST_BOOTSTRAP_TOKEN},
    )
    client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    response = client.put("/api/v1/health/live", headers=csrf_headers(client))
    assert response.status_code == 405
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message", "details", "request_id"}


def test_409_envelope_shape_for_conflict(client: TestClient) -> None:
    # bootstrap_admin = Bootstrap + Login (setzt Session- und CSRF-Cookies).
    from tests.conftest import bootstrap_admin, csrf_headers

    client = bootstrap_admin(client)
    # Ein echter 409-Trigger: Username doppelt.
    created = client.post(
        "/api/v1/users",
        headers=csrf_headers(client),
        json={"username": "dup-user", "password": "dup-pass-12345", "role": "viewer"},
    )
    assert created.status_code == 201
    duplicate = client.post(
        "/api/v1/users",
        headers=csrf_headers(client),
        json={"username": "dup-user", "password": "dup-pass-12345", "role": "viewer"},
    )
    assert duplicate.status_code == 409
    body = duplicate.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["request_id"]
