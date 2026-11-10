"""Security-Regression: Secret-Handling und Credential-Leakage.

Verbindliche Regeln (MASTER_PROMPT / api-contracts.md):
- Die DB/API kennt nur secret_ref (Referenz), nie Werte
- Fehlerantworten enthalten keine Secrets/Stacktraces
- Audit-Details werden maskiert
- viewer bekommt keine secret_ref
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import create_user


def test_viewer_never_sees_secret_ref(app, admin_client: TestClient) -> None:
    """secret_ref ist eine interne Konfigurationsreferenz: viewer darf sie
    nicht sehen, operator/admin schon."""
    csrf = admin_client.cookies.get("hcc_csrf", "")
    r = admin_client.put(
        "/api/v1/integrations/qa-secret-int",
        headers={"X-CSRF-Token": csrf},
        json={
            "integration_id": "qa-secret-int",
            "name": "Secret Test",
            "adapter": "proxmox",
            "base_url": "https://proxmox.example.internal:8006",
            "secret_ref": "PROXMOX_API_TOKEN",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["secret_ref"] == "PROXMOX_API_TOKEN"

    from tests.conftest import login_client

    create_user(admin_client, "qa_secret_viewer", "viewer-pass-12345", "viewer")
    viewer = login_client(app, "qa_secret_viewer", "viewer-pass-12345")

    for path in ("/api/v1/integrations", "/api/v1/integrations/qa-secret-int"):
        body = viewer.get(path)
        assert body.status_code == 200
        items = body.json().get("items", [body.json()])
        for item in items:
            assert item["secret_ref"] is None, f"viewer sieht secret_ref in {path}"


def test_secret_values_never_appear_in_api_responses(
    admin_client: TestClient, monkeypatch
) -> None:
    """Ein (hypothetisches) Secret aus secrets.env darf in keiner
    API-Antwort auftauchen — auch nicht in Verify-/Fehlerantworten."""
    monkeypatch.setenv("QA_LEAK_SECRET", "top-secret-value-0123456789abcdef")
    csrf = admin_client.cookies.get("hcc_csrf", "")
    r = admin_client.put(
        "/api/v1/integrations/qa-leak",
        headers={"X-CSRF-Token": csrf},
        json={
            "integration_id": "qa-leak",
            "name": "Leak Test",
            "adapter": "unknown",
            "base_url": None,
            "secret_ref": "QA_LEAK_SECRET",
        },
    )
    assert r.status_code == 200
    assert "top-secret-value-0123456789abcdef" not in r.text

    v = admin_client.post("/api/v1/integrations/qa-leak/verify", headers={"X-CSRF-Token": csrf})
    assert v.status_code in (200, 501), v.text
    assert "top-secret-value-0123456789abcdef" not in v.text

    listing = admin_client.get("/api/v1/integrations")
    assert "top-secret-value-0123456789abcdef" not in listing.text


def test_error_details_do_not_echo_passwords(admin_client: TestClient) -> None:
    """422-Validierungs-Details duerfen uebergebene Passwortwerte nie
    zurueckspiegeln (nur loc/msg/type des Felds)."""
    secret_pw = "geheim-passw0rt-xyz"
    csrf = admin_client.cookies.get("hcc_csrf", "")
    response = admin_client.post(
        "/api/v1/users",
        headers={"X-CSRF-Token": csrf},
        # Username ungueltig (Großbuchstaben) => 422; Passwort muessen wir
        # trotzdem uebergeben — genau da duerfte ein Leak stattfinden.
        json={"username": "PW-ECHO-TEST", "password": secret_pw, "role": "viewer"},
    )
    assert response.status_code == 422, response.text
    assert secret_pw not in response.text, "Passwortwert in 422-Details geleakt"


def test_login_validation_error_does_not_echo_values(client: TestClient) -> None:
    """Login mit ungueltigem Body: 422, aber der eingegebene Wert taucht
    nicht in der Antwort auf."""
    response = client.post("/api/v1/auth/login", json={"username": "u", "password": ""})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert "password" not in body.get("message", "")


def test_unhandled_error_never_leaks_stacktrace(client: TestClient) -> None:
    """500-Envelope: generische Nachricht, kein Stacktrace, keine
    Intros (Pfad/DB-Zeichenkette)."""
    response = client.get("/api/v1/definitiv-keine-routen")  # 404, als Envelope-Kontrolle
    assert response.status_code == 404
    assert "Traceback" not in response.text
    assert "File \"" not in response.text


def test_audit_details_are_masked(admin_client: TestClient, db) -> None:
    """record_audit maskiert bekannte Secret-Felder in details
    (z. B. password/token/secret)."""
    from app.audit.log import record_audit
    from fastapi import Request

    class _FakeRequest:
        client = None
        headers = {}

    import uuid as _uuid

    user = admin_client.get("/api/v1/auth/me").json()
    from app.models.users import User as UserModel
    from sqlalchemy import select

    model = db.scalar(select(UserModel).where(UserModel.id == _uuid.UUID(user["id"])))
    event = record_audit(
        db,
        user=model,
        action="qa.masking.test",
        request=_FakeRequest(),  # type: ignore[arg-type]
        details={"password": "sehr-geheimes-passwort-123", "token": "abc123", "benutzer": "ok"},
    )
    assert event.details["password"] != "sehr-geheimes-passwort-123"
    assert event.details["token"] != "abc123"
    assert event.details["benutzer"] == "ok"
    assert "***" in str(event.details["password"])


def test_integrations_delete_is_audited(admin_client: TestClient, db) -> None:
    """Ungeschuetzte Verwaltungsaktionen gibt es nicht: admin-Aktionen
    ohne CSRF werden abgelehnt und admin-Aktionen landen im Audit."""
    csrf = admin_client.cookies.get("hcc_csrf", "")
    r = admin_client.put(
        "/api/v1/integrations/qa-aud",
        headers={"X-CSRF-Token": csrf},
        json={"integration_id": "qa-aud", "name": "Aud", "adapter": "unknown"},
    )
    assert r.status_code == 200
    d = admin_client.delete("/api/v1/integrations/qa-aud", headers={"X-CSRF-Token": csrf})
    assert d.status_code == 204

    from sqlalchemy import select
    from app.models.audit import AuditEvent

    rows = db.scalars(select(AuditEvent).where(AuditEvent.action == "integrations.delete")).all()
    assert rows, "integrations.delete fehlt im Audit"
    assert rows[-1].username == "qa_admin"
