"""Erzeugt den stabilen OpenAPI-Contract aus der App (frozen, R0).

Aufruf (aus dem Repository-Root oder backend/):
    python scripts/generate-openapi.py

Aenderung des Contracts => Commit des neuen openapi.v1.json ist
Pflicht (reviewbares Diff), plus Entry in docs/api-contracts.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> None:
    settings = Settings(
        environment="development",
        database_url="sqlite://",
        bootstrap_token="contract-generation-token-0123456789",
        git_commit="contract-gen",
        log_level="WARNING",
    )
    app = create_app(settings)
    spec = app.openapi()
    out_path = BACKEND_DIR / "contracts" / "openapi.v1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out_path.write_text(rendered, encoding="utf-8")
    print(f"openapi.v1.json geschrieben: {out_path} ({len(spec.get('paths', {}))} Pfade)")


if __name__ == "__main__":
    main()
