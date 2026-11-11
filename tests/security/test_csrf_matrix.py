"""Security-Regression: CSRF (Double-Submit-Cookie) Matrix.

Verbindliche Semantik (docs/api-contracts.md §1, R0-frozen):
- state-aendernde Methoden (POST/PUT/PATCH/DELETE) unter /api/v1/
  benoetigen Session-Cookie UND X-CSRF-Token == hcc_csrf-Cookie
- Exemption: POST /auth/login, POST /auth/bootstrap
- Fehlschlag => 403 mit Error-Envelope
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _csrf_envelope(response) -> bool:
    """Erkennt die CSRF-403-Envelope (abgrenzbar zu RBAC-403)."""
    if response.status_code != 403:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return body.get("error", {}).get("code") == "forbidden" and "CSRF" in body.get("error", {}).get("message", "")


def _valid_csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("hcc_csrf", "")
    assert token, "CSRF-Cookie nach Login fehlt"
    return {"X-CSRF-Token": token}


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/users"),
        ("PATCH", "/api/v1/users/00000000-0000-0000-0000-000000000000"),
        ("PUT", "/api/v1/integrations/qa-int"),
        ("POST", "/api/v1/integrations/qa-int/verify"),
        ("DELETE", "/api/v1/integrations/qa-int"),
        ("POST", "/api/v1/auth/logout"),
    ],
)
def test_state_change_without_session_cookie_is_rejected(
    client: TestClient, admin_client: TestClient, method: str, path: str
) -> None:
    """Ohne Session-Cookie: 403 (CSRF), selbst mit validem Header-Wert."""
    token = admin_client.cookies.get("hcc_csrf", "whatever")
    response = client.request(method, path, headers={"X-CSRF-Token": token}, json={} if method != "PATCH" else None)
    assert _csrf_envelope(response), f"{method} {path}: CSRF-Ablehnung erwartet, bekam {response.status_code}"


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/users"),
        ("PUT", "/api/v1/integrations/qa-int"),
        ("POST", "/api/v1/integrations/qa-int/verify"),
        ("DELETE", "/api/v1/integrations/qa-int"),
        ("POST", "/api/v1/auth/logout"),
    ],
)
def test_state_change_with_missing_or_wrong_csrf_header_is_rejected(
    client: TestClient, admin_client: TestClient, method: str, path: str
) -> None:
    """Session vorhanden, aber Header fehlt oder stimmt nicht => 403."""
    csrf_cookie = admin_client.cookies.get("hcc_csrf", "")
    for bad_header in ({}, {"X-CSRF-Token": "absolutes-geschmeide-token"}):
        response = client.request(
            method,
            path,
            cookies={"hcc_session": admin_client.cookies.get("hcc_session", ""), "hcc_csrf": csrf_cookie},
            headers=bad_header,
            json={} if method == "POST" else None,
        )
        assert _csrf_envelope(response), (
            f"{method} {path} mit Header {bad_header}: CSRF-403 erwartet, bekam {response.status_code}"
        )


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/api/v1/auth/logout", None),
        (
            "PUT",
            "/api/v1/integrations/qa-int",
            {
                "integration_id": "qa-int",
                "name": "QA Integration",
                "adapter": "unknown",
                "base_url": None,
                "secret_ref": None,
            },
        ),
        ("DELETE", "/api/v1/integrations/qa-int", None),
    ],
)
def test_state_change_with_valid_csrf_is_not_rejected_by_csrf(
    client: TestClient, admin_client: TestClient, method: str, path: str, body: dict | None
) -> None:
    """Valide Session + matching Header: die CSRF-Schicht darf NICHT
    ablehnen (403/404/Geschaeftsfehler sind moeglich, CSRF-403 nicht)."""
    response = client.request(
        method,
        path,
        cookies={
            "hcc_session": admin_client.cookies.get("hcc_session", ""),
            "hcc_csrf": admin_client.cookies.get("hcc_csrf", ""),
        },
        headers={"X-CSRF-Token": admin_client.cookies.get("hcc_csrf", "")},
        json=body,
    )
    assert not _csrf_envelope(response), f"{method} {path}: CSRF-403 trotz validem Double-Submit"


@pytest.mark.parametrize("path", ["/api/v1/auth/login", "/api/v1/auth/bootstrap"])
def test_exemptions_do_not_require_csrf(path: str, client: TestClient) -> None:
    """login/bootstrap duerfen OHNE Session und OHNE CSRF-Header angefragt
    werden (Antwort darf 4xx aus anderen Gruenden sein, nur keine CSRF-403)."""
    response = client.post(path, json={"username": "x", "password": "y", "token": "z" * 16})
    assert not _csrf_envelope(response), f"{path}: CSRF-Exemption verletzt"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/users",
        "/api/v1/integrations",
        "/api/v1/resources",
        "/api/v1/audit",
        "/api/v1/auth/me",
        "/api/v1/health/live",
    ],
)
def test_read_endpoints_never_hit_csrf_layer(client: TestClient, path: str) -> None:
    """GET-Requests duerfen nie von der CSRF-Schicht abgelehnt werden
    (Auth-401 ist erwartbar, CSRF-403 nicht)."""
    response = client.get(path)
    assert not _csrf_envelope(response), f"GET {path}: CSRF-403 unerwaertet"
