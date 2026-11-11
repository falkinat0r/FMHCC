"""Secrets-Masking-Tests (R1, Agent 1: Backend Core & Security).

Audit-Details und Log-Payloads duerfen keine Secret-Werte enthalten.
``mask_fields`` maskiert bekannte Felder rekursiv; ``mask_value`` verkuerzt
Strings. Hier: erweiterte Feldliste + Rekursion + dass ``secret_ref``
(NAMEN, nicht Werte) NICHT maskiert wird, weil es nur eine Referenz ist.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit.log import record_audit
from app.auth.hashing import hash_password
from app.logging_setup import mask_fields, mask_value
from app.models.audit import AuditEvent
from app.models.users import Role, User
from tests.conftest import bootstrap_admin, csrf_headers


def test_mask_value_short_and_long() -> None:
    assert mask_value("abc") == "***"
    masked = mask_value("supersecretvalue")
    assert masked != "supersecretvalue"
    assert "***" in masked
    assert masked.startswith("supe")
    assert masked.endswith("alue")


def test_mask_fields_masks_known_secret_keys() -> None:
    data = {
        "password": "pw-1234567890",
        "password_hash": "$argon2id$xxxx",
        "token": "tok-1234567890",
        "access_token": "at-1234567890",
        "refresh_token": "rt-1234567890",
        "secret": "sec-1234567890",
        "api_key": "key-1234567890",
        "client_secret": "cs-1234567890",
        "private_key": "pk-1234567890",
        "authorization": "Bearer abcdefgh1234",
        "cookie": "cookie-value-1234",
        "session_token": "st-1234567890",
        "csrf_token": "ct-1234567890",
        "bootstrap_token": "bt-1234567890",
        "username": "nicht-secret",
    }
    masked = mask_fields(data)
    for key in (
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "api_key",
        "client_secret",
        "private_key",
        "authorization",
        "cookie",
        "session_token",
        "csrf_token",
        "bootstrap_token",
    ):
        assert masked[key] != data[key], key
        assert "***" in masked[key], key
    # Nicht-Secret bleibt unveraendert
    assert masked["username"] == "nicht-secret"


def test_mask_fields_recurses_into_nested_dicts() -> None:
    # Rekursion: auch in verschachtelten Dicts werden exakt benannte
    # Secret-Felder maskiert (R0-Semantik: exakter Key-Match).
    data = {"credentials": {"api_key": "nested-api-key-1234", "password": "nested-pass-12345", "safe": "ok"}}
    masked = mask_fields(data)
    assert "***" in masked["credentials"]["api_key"]
    assert "***" in masked["credentials"]["password"]
    assert masked["credentials"]["safe"] == "ok"


def test_mask_fields_case_insensitive_key_match() -> None:
    masked = mask_fields({"Password": "uppercasevalue12"})
    assert "***" in masked["Password"]


def test_audit_details_are_masked_end_to_end(db) -> None:
    user = User(username="mask-user", role=Role.ADMIN, password_hash=hash_password("passwort-12345"))
    db.add(user)
    db.flush()
    record_audit(
        db,
        user=user,
        action="integrations.verify",
        details={"api_key": "AKIA-SECRET-VALUE-1234", "note": "ok"},
    )
    db.flush()
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "integrations.verify"))
    assert event is not None
    assert "AKIA-SECRET-VALUE-1234" not in str(event.details)
    assert "***" in event.details["api_key"]
    assert event.details["note"] == "ok"


def test_secret_ref_is_a_reference_name_not_masked(client: TestClient, db) -> None:
    # secret_ref ist der NAME einer Env-Variable (Referenz), kein Wert.
    # Er darf in API-Antworten erscheinen (nur Referenz), wird aber nicht
    # als Secret-Wert behandelt. Der WERT selbst wird nur vom Provider geloest.
    client = bootstrap_admin(client)
    response = client.put(
        "/api/v1/integrations/secretref-1",
        headers=csrf_headers(client),
        json={
            "integration_id": "secretref-1",
            "name": "SecretRef",
            "adapter": "proxmox",
            "secret_ref": "PROXMOX_API_TOKEN",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["secret_ref"] == "PROXMOX_API_TOKEN"
    # Kein Wert darf im Body auftauchen.
    assert "PROXMOX_API_TOKEN_VALUE" not in str(body)
