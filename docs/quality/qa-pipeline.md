# R1 — QA-Pipeline (QA, Agent 5)

Stand: 2026-11-10 · Branch `feature/qa`

Ein Kommando, alle Gates. Zwei äquivalente Runner:

- **`scripts/qa/run-qa.sh`** — bash (CI / Linux).
- **`scripts/qa/run-qa.ps1`** — Windows-PowerShell-Spiegel (lokale Entwicklung).

Beide laufen aus dem Repository-Root, leiten sich selbst den Root ab und
beenden mit:

- **0** = alle Gates bestanden
- **1** = mindestens ein Gate **FAILED**
- **2** = keine Failure, aber mindestens ein Gate **BLOCKED**
  (keine belastbare Aussage — z. B. Audit ohne Netzwerk)

> **Prinzip:** Ein Gate, das nicht sauber ausgeführt werden kann, ist
> **keine** Bestätigung. BLOCKED wird ausdrücklich als "grün mit Reserve"
> behandelt, nicht als grüner Pass.

## 1. Gates

| # | Gate | Werkzeug | BLOCKED wenn |
| --- | --- | --- | --- |
| 1 | Secret-Scan | `scripts/qa/scan_secrets.py` | kein Python |
| 2 | Backend-Lint | `uv run ruff check` | kein `uv` |
| 3 | Backend-Unit-Tests | `uv run pytest` (backend) | kein `uv` |
| 4 | OpenAPI-Drift | `scripts/qa/check_openapi_drift.py` | kein `uv` / Import-Fehler |
| 5 | QA-Suite | `pytest tests/` (Root) | kein `uv` |
| 6 | Frontend (tsc/build/vitest/lint) | node/npm | kein `node`/`npm` |
| 7a | Dependency-Audit (Python) | `uv audit` | Netzwerk-/Tool-Fehler (≠ vuln) |
| 7b | Dependency-Audit (npm, prod) | `npm audit --omit=dev` | Netzwerk-/Tool-Fehler (≠ vuln) |
| 8 | Deploy-Invarianten | `scripts/qa/check_deploy_artifacts.py` | kein Python / Datei fehlt |

**Audit-Semantik (Gate 7):** Exit 0 = clean, 1 = verwundbare Abhängigkeit,
2 = Ausführung fehlgeschlagen. Ein Netzwerkfehler beim Audit wird deshalb
**BLOCKED** (nicht grün) gewertet; ein erkanntes CVE ist eine **Failure**.

## 2. Ausführung

```bash
# Linux / CI
bash scripts/qa/run-qa.sh

# Windows (lokal)
powershell -ExecutionPolicy Bypass -File scripts\qa\run-qa.ps1
```

- **Frontend ohne System-Node:** Der Runner findet Node automatisch in
  `tools/node-<ver>-win-x64/` (git-ignoriert) oder nutzt `HCC_NODE_BIN`.
- **Python:** Bevorzugt die `uv`-Venv (`uv run --project backend python`)
  für Reproduzierbarkeit; sonst System-Python.
- Der Runner bricht nicht ab, wenn ein Gate fällt — alle Gates laufen,
  am Ende steht die komplette Fehlerliste.

## 3. CI (`.github/workflows/qa.yml`)

- Triggers: Push/PR gegen `main` + `workflow_dispatch`.
- Setup: `uv` (setup-uv), `uv sync --frozen` in `backend/`, Node 22,
  `npm install` in `frontend/` (bis Lockfile committet, dann `npm ci`).
- Führt `bash scripts/qa/run-qa.sh` aus und behandelt **auch Exit 2 als
  Failure** in CI: ein im Runner unbelastbares Audit darf dort keinen
  stillen Green-Pass geben.
- Log als Artefakt `qa-pipeline-log`.

## 4. Neue QA-Tools (R1)

| Tool | Zweck |
| --- | --- |
| `scripts/qa/scan_secrets.py` | Statische Secret-Erkennung (Stdlib-only), Allowlist mit dokumentierten Freigaben |
| `scripts/qa/check_openapi_drift.py` | App-OpenAPI ↔ eingefrorener Snapshot, **schreibfrei** (diff-only) |
| `scripts/qa/check_deploy_artifacts.py` | Statische systemd/nginx/deploy-lxc-Invarianten (kein System-Kontakt) |
| `scripts/qa/run-qa.sh` / `.ps1` | Gate-Orchestrierung mit 0/1/2-Semantik |
| `tests/e2e/e2e-smoke.sh` | E2E-Smoke **nur im Ziel-LXC** (nie in CI) |

## 5. R1-Erstlauf (ausgeführt)

- Windows-Runner: **alle 12 Gates OK → Exit 0**.
- bash-Runner: **nicht ausgeführt** (kein Linux-Runner in der QA-Umgebung),
  statisch als CI-Laufpfad vorbereitet. Das ist bewusst als Risiko gemeldet
  (deployment-review D1), nicht als Bestätigung.

## 6. Wartung / Erweiterung

- Neues Gate: Funktion `run_gate` (sh) bzw. `Invoke-Gate` (ps1) mit passendem
  Namen und — falls relevant — `blocked_on_rc2`.
- Secret-Scanner: Falsch-positiv nur über die `ALLOWLIST` mit Begründung
  freigegeben, nie durch Muster-Entfernung.
- Deploy-Checker: Invarianten-Regeln sind bewusst konservativ; bei
  bewusster Änderung des Deployment-Vertrags **zunächst die Doku**
  (`docs/DEPLOYMENT_PLAYBOOK.md`) ändern, dann die Regel.
