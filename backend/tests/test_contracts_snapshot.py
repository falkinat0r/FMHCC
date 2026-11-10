"""Contract-Snapshot-Tests: verhindern stillschweigende API-Vertragsaenderungen (R0).

Die OpenAPI-Spezifikation ist der verbindliche Contract. Jedes
Contract-Release erfordert:
1. gezielte Aenderung der Contracts
2. ``python scripts/generate-openapi.py``
3. Review des Diff in ``backend/contracts/openapi.v1.json``
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.main import create_app

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"


def _make_app():
    settings = Settings(
        environment="development",
        database_url="sqlite://",
        bootstrap_token="snapshot-test-token-0123456789",
        git_commit="snapshot",
    )
    return create_app(settings)


def _spec() -> dict:
    return _make_app().openapi()


def test_openapi_snapshot_matches_committed_contract() -> None:
    spec = _spec()
    rendered = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    committed = (CONTRACTS_DIR / "openapi.v1.json").read_text(encoding="utf-8")
    assert rendered == committed, (
        "OpenAPI-Spezifikation weicht vom committed Contract ab. "
        "Bewusst? Dann scripts/generate-openapi.py ausfuehren und das Diff reviewen."
    )


def test_all_paths_are_versioned() -> None:
    spec = _spec()
    assert spec["paths"]
    for path in spec["paths"]:
        assert path.startswith("/api/v1/"), f"Unversionierter Pfad: {path}"


def test_openapi_documented_endpoints_exist() -> None:
    spec = _spec()
    required = [
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/version",
        "/api/v1/auth/bootstrap",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/users",
        "/api/v1/integrations",
        "/api/v1/resources",
        "/api/v1/audit",
    ]
    for path in required:
        assert path in spec["paths"], f"Fehlender gefrorener Endpoint: {path}"


def test_error_envelope_and_pagination_are_documented() -> None:
    spec = _spec()
    schemas = spec["components"]["schemas"]
    assert "ErrorEnvelope" in schemas
    assert "ErrorCode" in schemas
    # Paged-Envelope existiert (generisch; Name enthaelt 'Paged')
    assert any(name.startswith("Paged") for name in schemas)
