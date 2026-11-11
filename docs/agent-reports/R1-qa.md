# R1 — Agent-Report: QA / Security / Deployment (Agent 5)

Stand: 2026-11-10 · Branch `feature/qa` · kein Merge, keine produktiven Änderungen

## 1. Mandat (R1-Agent-5) und Abnahme

| Aufgabe | Status |
| --- | --- |
| Baseline-Review R0 | ✅ `docs/quality/R1-baseline-review.md` |
| Testautomatisierung + CI | ✅ `tests/` (118 Tests), `scripts/qa/`, `.github/workflows/qa.yml` |
| LXC-Deployment-Concept Review + Härtung | ✅ `docs/quality/deployment-review.md` + Artefakt-Änderungen |
| Security-Review mit Findings | ✅ `docs/quality/security-findings.md` (10 Findings, 0 kritisch) |
| Integrations-Testmatrix | ✅ `docs/quality/integration-matrix.md` |
| QA-Pipeline-Doku | ✅ `docs/quality/qa-pipeline.md` |

## 2. Kernergebnisse (alles echt ausgeführt)

1. **Baseline:** Backend 63/63 grün (unverändert). Frontend wurde **erstmals**
   ausgeführt: Typecheck/Build grün, 1 Vitest-Defekt und eine ESLint-Konfig
   wurden in QA-Bereichsdateien repariert (Test + Lint-Konfig, keine
   Produktlogik). OpenAPI-Snapshot identisch zur App (Drift-Check schreibfrei).
2. **QA-Suite:** 118 Tests unter `tests/` (Contract, RBAC, CSRF,
   Session/Cookie, Auth-Härtung, Secret-Leakage, Input-Validierung) —
   alle bestanden.
3. **Security-Review:** 10 Findings (S1–S10), keine kritisch, keine mit
   aktivem Exploit-Pfad. Priorität: **S1** (Audit-FK NULL bei neuer
   Integration) und **S3** (Rate-Limit-Bucket pro Loopback-IP hinter nginx).
4. **Deployment-Review:** systemd-Unit um `ExecStartPost`-Health-Probe +
   `TimeoutStartSec=180` erweitert; `deploy-lxc.sh` um Preflight, `--list`,
   `--rollback <sha>`; statische Invarianten-Checks als Pipeline-Gate;
   E2E-Smoke-Skript für das Ziel-LXC vorbereitet (in R1 nicht ausgeführt —
   keine produktiven Änderungen).
5. **CI:** `.github/workflows/qa.yml` + zweisprachiger Pipeline-Runner
   (`run-qa.sh` / `run-qa.ps1`), 12 Gates, Exit-Semantik 0/1/2
   (BLOCKED ≠ grün). Windows-Runner: **alle 12 Gates grün, Exit 0**.

## 3. Betroffene Dateien

### Neu (QA-Bereich, Agent 5)
- `tests/pytest.ini`, `tests/__init__.py`, `tests/conftest.py`
- `tests/contract/{__init__.py,test_openapi_contract.py}`
- `tests/security/{__init__.py,test_csrf_matrix.py,test_rbac_matrix.py,test_session_security.py,test_secret_leakage.py,test_auth_hardening.py,test_input_validation.py}`
- `tests/e2e/e2e-smoke.sh` (LXC-only)
- `scripts/qa/{scan_secrets.py,check_openapi_drift.py,check_deploy_artifacts.py,run-qa.sh,run-qa.ps1}`
- `.github/workflows/qa.yml`
- `docs/quality/{R1-baseline-review,security-findings,deployment-review,integration-matrix,qa-pipeline}.md`
- `docs/agent-reports/R1-qa.md` (diese Datei)
- `deploy/systemd/health-probe.sh` (Deploy-Artefakt)

### Geändert (QA-/Deploy-Bereich, Agent 5)
- `deploy/systemd/hcc-api.service` — `ExecStartPost`, `TimeoutStartSec=180`
- `scripts/deploy-lxc.sh` — Preflight, `--list`, `--rollback`, Probe-Install
- `frontend/eslint.config.js` — QA-Befund: fehlende recommended-Konfig +
  Vitest-Globals (Lint-Konfig, keine Produktlogik)
- `frontend/src/api/client.test.ts` — QA-Befund: Content-Type-Erwartung
  korrigiert, POST-ohne-Body-Case ergänzt (Testdatei)

### Nicht berührt (bewusst)
- `backend/app/**` (Produktcode — Findings nur dokumentiert)
- `backend/contracts/**`, `backend/alembic/**` (frozen)
- `docs/api-contracts.md` etc. (Contract-Doku — Abweichungen als Findungen S2 dokumentiert)

## 4. Ausgeführte Test-Schritte (Belege)

| Schritt | Befehl | Ergebnis |
| --- | --- | --- |
| Backend-Unit | `uv run pytest` (backend/) | 63 passed |
| QA-Suite | `uv run --project backend python -m pytest tests -q` | 118 passed |
| OpenAPI-Drift | `uv run --project backend python scripts/qa/check_openapi_drift.py` | OK, 15 Pfade identisch |
| Secret-Scan | `uv run --project backend python scripts/qa/scan_secrets.py` | 0 Befunde |
| Deploy-Invarianten | `uv run --project backend python scripts/qa/check_deploy_artifacts.py` | OK |
| Frontend | `npx tsc -b --noEmit`, `npm run build`, `npx vitest run`, `npm run lint` | alle grün |
| Dependency-Audits | `uv audit --project backend`, `npm audit --omit=dev` | clean |
| Pipeline (Windows) | `powershell -File scripts\qa\run-qa.ps1` | 12/12 Gates OK, **Exit 0** |
| Syntax (bash) | `bash -n` für alle neuen/änderteren Shell-Skripte | OK |

## 5. Offene Risiken

| # | Risiko | Mitnahme |
| --- | --- | --- |
| R1 | `run-qa.sh` (bash/CI-Pfad) nur statisch geprüft, nicht ausgeführt (kein Linux-Runner in der QA-Umgebung) | Läuft bei Push/PR in GitHub Actions; Log als Artefakt |
| R2 | `deploy-lxc.sh` nie unter Linux ausgeführt | E2E-Smoke + Preflight/Rollback vorbereitet; Ausführung erst nach Merge im LXC |
| R3 | Security-Findings S1/S3 sind **nicht** fixt (Produktcode, QA-Scope) | Doku + Priorisierung; Fix in R1-Backend-Stream oder Follow-up |
| R4 | Kein `package-lock.json` (S9/B2) | CI nutzt `npm install`; Commit des Lockfiles dem Frontend-Workstream empfohlen |
| R5 | Rate-Limiting in-memory, Bootstrap-Token bleibt nach Nutzung im Env-File | Dokumentiert (S3/D3); Betriebsthemen |
| R6 | `frontend/package-lock.json` wurde durch den QA-Build lokal erzeugt, ist aber **nicht** committet (Ownership: Frontend) | In `git status` sichtbar als untracked; vor dem Merge entfernen oder bewusst übergeben |

## 6. Integrationshinweise

1. **Keine Contract-Änderungen** von R1-Agent-5. S2 (`method_not_allowed`)
   wäre eine — dann über `docs/proposals/`, nicht direkt.
2. `tests/` nutzt `tests/pytest.ini` (`pythonpath = ../backend`) und darf
   nur über den QA-Runner (`uv run --project backend python -m pytest tests`)
   oder den Root-`pytest.ini`-Mechanismus laufen; Kollision mit
   `backend/pytest.ini` ist bewusst getrennt (getrennte rootdirs).
3. Windows-Entwicklung: `run-qa.ps1` bleibt **ASCII-only** (cp1252-Falle,
   im Header dokumentiert). Node via `tools/node-*-win-x64/` (git-ignoriert)
   oder `HCC_NODE_BIN`.
4. CI: Nach Commit des Frontend-Lockfiles `npm install` → `npm ci` in
   `qa.yml` umstellen (Kommentar vorhanden).
5. Nach Merge im LXC: `deploy-lxc.sh --start`, dann `tests/e2e/e2e-smoke.sh`
   (root, mit `HCC_SMOKE_ADMIN`/`HCC_SMOKE_PASS`).

## 7. Commit

| Commit | Inhalt |
| --- | --- |
| `7a8b3a9` | QA-Suite, QA-Tools, CI, Deploy-Artefakt-Änderungen, `docs/quality/*` |
| (dieser) | Dieser Report (referenziert `7a8b3a9`) |
