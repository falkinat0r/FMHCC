"""Contract-Tests: pinnen den eingefrorenen OpenAPI-Snapshot (R0).

Prueft den Snapshot ``backend/contracts/openapi.v1.json`` gegen die
verbindliche Endpunkt-Tabelle und Schema-Regeln aus
``docs/api-contracts.md``. Laeuft rein statisch (keine App, keine DB)
und ist damit unabhaengig von den parallelen Agenten-Implementierungen.

Drift zwischen Code und Snapshot wird zusaezlich von
``backend/tests/test_contracts_snapshot.py`` erwischt; hier wird nur
der Inhalt des Snapshots gegen die dokumentierten Contracts geprueft.
"""

from __future__ import annotations

import json
import pathlib

SNAPSHOT = pathlib.Path(__file__).resolve().parents[2] / "backend" / "contracts" / "openapi.v1.json"

# Verbindliche Routen-Tabelle (docs/api-contracts.md §4, R0-frozen).
EXPECTED_PATHS: dict[str, set[str]] = {
    "/api/v1/health/live": {"get"},
    "/api/v1/health/ready": {"get"},
    "/api/v1/version": {"get"},
    "/api/v1/auth/bootstrap": {"post"},
    "/api/v1/auth/login": {"post"},
    "/api/v1/auth/logout": {"post"},
    "/api/v1/auth/me": {"get"},
    "/api/v1/users": {"get", "post"},
    "/api/v1/users/{user_id}": {"patch"},
    "/api/v1/integrations": {"get"},
    "/api/v1/integrations/{integration_id}": {"get", "put", "delete"},
    "/api/v1/integrations/{integration_id}/verify": {"post"},
    "/api/v1/resources": {"get"},
    "/api/v1/resources/{resource_id}": {"get"},
    "/api/v1/audit": {"get"},
}


def _snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _schemas(doc: dict) -> dict:
    return doc["components"]["schemas"]


# ---------------------------------------------------------------------------
# Routenplan
# ---------------------------------------------------------------------------


def test_exactly_the_frozen_path_set() -> None:
    doc = _snapshot()
    assert set(doc["paths"].keys()) == set(EXPECTED_PATHS), "Routenplan weicht vom R0-Freeze ab"


def test_every_path_uses_expected_methods_only() -> None:
    doc = _snapshot()
    for path, methods in EXPECTED_PATHS.items():
        allowed = {"get", "post", "put", "patch", "delete", "head", "options"}
        present = {m for m in doc["paths"][path] if m in allowed}
        assert present == methods, f"{path}: erwartet {methods}, gefunden {present}"


def test_all_paths_are_versioned() -> None:
    for path in _snapshot()["paths"]:
        assert path.startswith("/api/v1/"), f"Nicht versionierter Pfad: {path}"


def test_no_secret_values_in_snapshot() -> None:
    """Der Contract darf keine Secret-Werte/Verbindungszugänge enthalten
    (Feldnamen wie 'password' sind Teil der Schema-Dokumentation und OK)."""
    raw = SNAPSHOT.read_text(encoding="utf-8")
    for forbidden in ("postgresql+psycopg://", "postgres://", "Bearer ", "api_key="):
        assert forbidden not in raw, f"Snapshot enthaelt unerwartetes Muster: {forbidden!r}"


# ---------------------------------------------------------------------------
# Error-Envelope (frozen)
# ---------------------------------------------------------------------------


def test_error_envelope_schemas_are_documented() -> None:
    schemas = _schemas(_snapshot())
    for name in ("ErrorEnvelope", "ErrorBody", "ErrorCode"):
        assert name in schemas, f"Error-Envelope-Schema fehlt: {name}"

    body = schemas["ErrorBody"]
    assert set(body["required"]) == {"code", "message", "request_id"}
    assert "details" in body["properties"], "details-Feld muss dokumentiert sein"


def test_error_code_enum_covers_documented_codes() -> None:
    """Alle in docs/api-contracts.md §2 genannten Codes muessen existieren."""
    codes = set(_schemas(_snapshot())["ErrorCode"]["enum"])
    documented = {
        "validation_error",
        "unauthenticated",
        "forbidden",
        "not_found",
        "conflict",
        "rate_limited",
        "not_implemented",
        "internal_error",
    }
    assert documented <= codes, f"Fehlende Error-Codes: {documented - codes}"


# ---------------------------------------------------------------------------
# Paging-Envelope (frozen)
# ---------------------------------------------------------------------------


def test_paged_envelope_shape() -> None:
    schemas = _schemas(_snapshot())
    paged = schemas["Paged_IntegrationOut_"]
    assert set(paged["properties"].keys()) == {"items", "page", "page_size", "total", "total_pages"}


def test_all_list_endpoints_use_paged_response() -> None:
    """Alle Listen-Endpunkte antworten mit der Paged_*-Envelope (§3)."""
    doc = _snapshot()
    collection_gets = ("/api/v1/users", "/api/v1/integrations", "/api/v1/resources", "/api/v1/audit")
    for path in collection_gets:
        responses = doc["paths"][path]["get"].get("responses", {})
        ok = responses.get("200", {})
        content = ok.get("content", {}).get("application/json", {})
        ref = content.get("schema", {}).get("$ref", "")
        assert ref.startswith("#/components/schemas/Paged_"), f"{path}: kein Paged-*: {ref}"


# ---------------------------------------------------------------------------
# Fachliche Enums (frozen)
# ---------------------------------------------------------------------------


def test_role_enum() -> None:
    assert set(_schemas(_snapshot())["Role"]["enum"]) == {"viewer", "operator", "admin"}


def test_resource_status_enum_is_exactly_five() -> None:
    """Keine zusätzlichen Zustände — fachliche Trennung (MASTER_PROMPT §A)."""
    assert set(_schemas(_snapshot())["ResourceStatus"]["enum"]) == {
        "healthy",
        "degraded",
        "down",
        "unknown",
        "not_configured",
    }


def test_resource_source_enum() -> None:
    assert set(_schemas(_snapshot())["ResourceSource"]["enum"]) == {"api", "manual", "inferred"}


def test_adapter_kind_enum() -> None:
    assert set(_schemas(_snapshot())["AdapterKind"]["enum"]) == {
        "proxmox",
        "truenas",
        "pihole",
        "tailscale",
        "docker",
        "monitoring",
        "homeassistant",
        "unknown",
    }


def test_verify_status_enum() -> None:
    """docs/api-contracts.md §5: ok | not_implemented sind Pflicht; die
    Adapter-States liefern die feingliedrige Untermenge."""
    values = set(_schemas(_snapshot())["VerifyStatus"]["enum"])
    assert "ok" in values and "not_implemented" in values
    assert values <= {
        "ok",
        "unreachable",
        "auth_failed",
        "timeout",
        "api_error",
        "version_unsupported",
        "not_configured",
        "not_implemented",
    }


# ---------------------------------------------------------------------------
# Wichtige Schemas (docs/api-contracts.md §5)
# ---------------------------------------------------------------------------


def test_integration_create_validation_rules() -> None:
    schema = _schemas(_snapshot())["IntegrationCreate"]
    props = schema["properties"]
    assert props["integration_id"]["pattern"] == r"^[a-z0-9][a-z0-9-]*$"
    assert props["integration_id"]["minLength"] == 3
    assert props["integration_id"]["maxLength"] == 64
    # secret_ref: anyOf[string|null]; das String-Glied muss Pattern + Laenge tragen
    ref_variants = props["secret_ref"]["anyOf"]
    string_variant = next(v for v in ref_variants if v.get("type") == "string")
    assert string_variant["maxLength"] == 128
    assert string_variant["pattern"] == r"^[A-Za-z][A-Za-z0-9_]{0,127}$"


def test_bootstrap_request_requires_long_token() -> None:
    """Bootstrap-Token: mind. 16 Zeichen (einmaliges Setup-Secret)."""
    schema = _schemas(_snapshot())["BootstrapRequest"]
    assert schema["properties"]["token"]["minLength"] >= 16


def test_password_fields_bounded() -> None:
    for name, min_len in (("LoginRequest", 1), ("BootstrapRequest", 10), ("UserCreate", 10)):
        schema = _schemas(_snapshot())[name]
        pw = schema["properties"]["password"]
        assert pw.get("maxLength") == 200, f"{name}: password.maxLength muss 200 sein"
        assert pw.get("minLength") == min_len, f"{name}: password.minLength muss {min_len} sein"


def test_resource_out_identity_fields() -> None:
    """Identität (integration_id, resource_type, external_id) muss sichtbar sein."""
    props = _schemas(_snapshot())["ResourceOut"]["properties"]
    for field in ("integration_id", "resource_type", "external_id", "status", "source"):
        assert field in props, f"ResourceOut.{field} fehlt"


def test_audit_event_out_fields() -> None:
    props = _schemas(_snapshot())["AuditEventOut"]["properties"]
    for field in ("id", "username", "action", "ip_address", "user_agent", "details", "created_at"):
        assert field in props, f"AuditEventOut.{field} fehlt"


def test_integration_out_exposes_only_secret_ref() -> None:
    """API gibt niemals Secret-Werte, sondern nur Referenznamen aus."""
    props = _schemas(_snapshot())["IntegrationOut"]["properties"]
    assert "secret_ref" in props
    assert "secret" not in props
    assert "secret_value" not in props
