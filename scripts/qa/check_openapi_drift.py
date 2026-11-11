"""OpenAPI-Drift-Check (HCC QA, Agent 5).

Vergleicht den eingefrorenen Contract-Snapshot
``backend/contracts/openapi.v1.json`` mit der aktuell aus der App
generierten OpenAPI-Spezifikation. Der Snapshot wird NICHT
ueberschrieben (frozen Contract — Regel 3); bei Drift zeigt das
Skript ein Diff und beendet mit Exit-Code 1.

Exit-Code: 0 = identisch, 1 = Drift, 2 = Pruefung nicht moeglich.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
SNAPSHOT = BACKEND_DIR / "contracts" / "openapi.v1.json"
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    try:
        from app.config import Settings
        from app.main import create_app
    except Exception as exc:  # noqa: BLE001
        print(f"FEHLER: App-Import nicht moeglich: {exc}")
        return 2

    try:
        settings = Settings(
            environment="development",
            database_url="sqlite://",
            bootstrap_token="contract-generation-token-0123456789",
            git_commit="drift-check",
            log_level="WARNING",
        )
        app = create_app(settings)
        spec = app.openapi()
        rendered = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    except Exception as exc:  # noqa: BLE001
        print(f"FEHLER: OpenAPI-Generierung fehlgeschlagen: {exc}")
        return 2

    if not SNAPSHOT.is_file():
        print(f"FEHLER: Contract-Snapshot fehlt: {SNAPSHOT}")
        return 2

    committed = SNAPSHOT.read_text(encoding="utf-8")
    if committed == rendered:
        paths = len(spec.get("paths", {}))
        print(f"OK: OpenAPI-Drift frei ({paths} Pfade, Snapshot identisch).")
        return 0

    print("FEHLER: OpenAPI-Drift erkannt — der eingefrorene Snapshot ist nicht aktuell.")
    print(
        "  Bewusste Aenderung: scripts/generate-openapi.py ausfuehren, Diff reviewen,\n"
        "  Snapshot + docs/api-contracts.md im Commit dokumentieren (R1-Regel: kein\n"
        "  stillschweigendes Aenderen geteilter Contracts)."
    )
    diff = difflib.unified_diff(
        committed.splitlines(keepends=True),
        rendered.splitlines(keepends=True),
        fromfile="backend/contracts/openapi.v1.json (committed)",
        tofile="openapi (aktuell aus App)",
        n=2,
    )
    for line in list(diff)[:200]:
        print(line, end="")
    return 1


if __name__ == "__main__":
    sys.exit(main())
