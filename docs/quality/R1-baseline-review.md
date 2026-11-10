# R1 — Baseline-Review R0 (QA, Agent 5)

Stand: 2026-11-10 · Branch `feature/qa` · Repo-Root `hcc-qa`

## 1. Ziel

Den in R0 übergebenen Stand **erstmals vollständig, echt und reproduzierbar
ausführen** (Backend, Frontend, Contracts, Deploy-Artefakte) und die Ausgangs-
qualität als belastbare Basis für R1-Veränderungen festhalten.

## 2. Ausgangslage R0

| Aspekt | Status R0 |
| --- | --- |
| Backend (FastAPI) | 63 Unit-/Contract-Tests, `uv run pytest` grün |
| Frontend (React/Vite) | **noch nie gebaut/ausgeführt** (kein Node in der QA-Umgebung) |
| OpenAPI-Contract | `backend/contracts/openapi.v1.json` eingefroren + Snapshot-Test |
| Deployment | 7-stufiges `deploy-lxc.sh` + systemd-Unit + nginx-Konfig, **nie unter Linux ausgeführt** |
| CI | keine |
| QA-/Sicherheitstests außerhalb `backend/tests` | keine |

## 3. Erstausführung (R1, alle Ergebnisse echt)

### 3.1 Backend
- `uv run pytest` in `backend/`: **63 passed** (keine Änderung gegenüber R0).
- `uv run ruff check`: clean (Konfiguration in `backend/pyproject.toml`,
  PEP-695-Rules bewusst ignoriert, weil sie generierte Schema-Namen und damit
  den eingefrorenen Contract-Snapshot brechen würden).

### 3.2 Frontend (Erstausführung — Node v22.23.4 lokal in `tools/`, git-ignoriert)
| Schritt | Ergebnis R0-Erstlauf | Ergebnis nach QA-Reparatur |
| --- | --- | --- |
| `npx tsc -b --noEmit` | ✅ bestanden | ✅ bestanden |
| `npm run build` (vite) | ✅ bestanden | ✅ bestanden |
| `npx vitest run` | 6/7 — **1 Defekt** | 7/7 |
| `npm run lint` (eslint 9) | ❌ **Fehler** (Konfig) | ✅ bestanden |

**R0-Defekte, die in QA-Bereichsdateien behoben wurden** (keine Produkt-Logik):
1. `frontend/src/api/client.test.ts`: testete einen `Content-Type`-Header, den
   der Client für POST *ohne* Body nicht setzt (bewusstes, dokumentiertes
   Verhalten). Test angepasst + POST-ohne-Body-Case ergänzt.
2. `frontend/eslint.config.js`: `tseslint.configs.recommended` fehlte und die
   Vitest-Globals (jest-globals-Setup) waren nicht für ESLint registriert →
   Lint lief nicht sauber. Konfig ergänzt (Test-/Tooling-Konfig, kein
   Produktcode).

### 3.3 Contract
- `backend/contracts/openapi.v1.json` deckt 15 Pfade ab; Snapshot-Test
  (`backend/tests/test_contracts_snapshot.py`) grün.
- Drift-Check (neu: `scripts/qa/check_openapi_drift.py`, **schreibfrei**):
  App-Generated-OpenAPI = Snapshot, identisch.

### 3.4 Deployment (statisch — kein Linux in QA-Umgebung)
- `scripts/deploy-lxc.sh`: 7 Stufen, idempotent, root-/Debian-Check,
  Zufalls-Bootstrap-Token, 0640/0600-Rechte. **Noch nie ausgeführt** →
  R1 ergänzt Preflight, `--list`, `--rollback` und eine systemd-Health-Probe
  (siehe `deployment-review.md`).
- Statische Invarianten-Checks (`scripts/qa/check_deploy_artifacts.py`): nach
  R1-Verbesserungen grün.

## 4. R0-Befunde (übernommen in R1)

| # | Befund | Status R1 |
| --- | --- | --- |
| B1 | Frontend nie gebaut, kein Node-Pfad dokumentiert | Erstausführung erfolgt; QA-Pipeline prüft Typecheck/Build/Vitest/Lint |
| B2 | Kein `package-lock.json` committet → keine reproduzierbaren Frontend-Abhängigkeiten | Offener Befund (Findung S9); CI nutzt bis zum Commit `npm install` statt `npm ci` |
| B3 | Rate-Limiting in-memory (Single-Instance-Annahme) | Offener Befund (Findung S3), dokumentiert |
| B4 | Bootstrap-Token bleibt nach Nutzung in `/etc/hcc/hcc.env` | Offener Befund (deployment-review D3), R1-Doku + Smoke-Doku weisen darauf hin |
| B5 | Enum-Persistenz über `values_callable` gelöst (R0) | Regressionstest in QA-Suite |
| B6 | Deploy-Script nie unter Linux geprüft | R1: Preflight/Rollback/Health-Probe + E2E-Smoke für das LXC |
| B7 | Kein CI, keine automatisierte QA-Gate-Kette | R1: `scripts/qa/run-qa.{sh,ps1}` + `.github/workflows/qa.yml` |

## 5. Konsequenzen für R1

- Alle R1-Änderungen werden gegen die Pipeline aus `qa-pipeline.md` gespielt
  (12 Gates, Exit-Semantik 0/1/2).
- QA-Suite unter `tests/` (Repository-Root) ist der dauerhafte
  Sicherheits-/Contract-/RBAC-Regressionsschutz (118 Tests, alle bestanden).
- Offene R0-Befunde bleiben sichtbar (Section 4) — R1 baut sie nicht still
  aus, sondern dokumentiert sie als Risiko.
