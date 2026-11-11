# R1 — Integrationsmatrix (Preflight, Phase A)

**Stand:** 2026-11-11 · **Integrationsbranch:** `integration/r1` (Basis `c86c3a4` = `master`, R0 Foundation + Handoff)
**Erstellt:** Integrations-/Release-Engineering (R1), vor dem ersten Merge.
**Grundlage:** AGENTS.md, MASTER_PROMPT.md, docs/architecture.md, docs/api-contracts.md,
docs/foundation-handoff.md, docs/PARALLEL_WORKFLOW.md, agent-tasks/01–05,
Agent-Reports (R1-backend, R1-proxmox, R1-telemetry, R1-frontend, R1-qa),
Proposals (7×), Security-Findings (S1–S10), Deployment-Review.

## 1. Ausgangslage Git

| Worktree | Branch | Tip | Status |
| --- | --- | --- | --- |
| `Documents/HCC` | `master` | `c86c3a4` | clean (Ziel-Branch, **nicht** angefasst) |
| `hcc-foundation` | `foundation` | `c86c3a4` | clean |
| `hcc-auth` | `feature/auth` | `991d047` | clean |
| `hcc-proxmox` | `feature/proxmox` | `0799a83` | clean |
| `hcc-telemetry` | `feature/telemetry` | `5c06127` | clean |
| `hcc-frontend` | `feature/frontend` | `58899ef` | clean |
| `hcc-qa` | `feature/qa` | `b1a2a58` | clean (1 untracked: `frontend/package-lock.json` aus QA-Build — siehe §4.6) |
| `hcc-integration` | `integration/r1` | `c86c3a4` | clean (Arbeitsbereich) |

- Alle fünf Feature-Branches basieren auf `c86c3a4` (`master`); **keine Kreuz-Merges**
  zwischen Feature-Branches (verifiziert via `git log --graph --all`).
- Keine nicht-committeten Änderungen in den Feature-Worktrees (nur das untracked
  Lockfile in `hcc-qa`, bekannt als QA-Risiko R6).
- R0-Baseline vor dem ersten Merge (in `hcc-integration/backend`):
  `uv run --extra dev pytest -q` → **63 passed** (alle grün).

## 2. Feature-Branch-Übersicht (Commits, Scope, self-reported Tests)

| # | Branch | Commits | Scope (gekürzter Dateibesitz) | Self-reported Testlauf |
| --- | --- | --- | --- | --- |
| 1 | `feature/auth` | `f6eb853` (Code), `991d047` (Report) | `app/auth`, `app/users`, `app/actions/` (neu), `app/api/v1/{auth,health,integrations}.py`, `app/audit/log.py`, `app/errors.py`, `app/logging_setup.py`, `app/__init__.py`, `tests/{auth,actions}`, `tests/test_{postgresql,secrets_masking,health_migration,integrations_r1,error_handling_r1}.py`, `tests/conftest.py`, `tests/test_version.py` | 121 passed, 1 skipped (Live-PG gependet) |
| 2 | `feature/proxmox` | `339a701` (Code), `0799a83` (Report) | **nur** `app/integrations/proxmox/**`, `app/inventory/proxmox/**`, `tests/proxmox/**`, Doku | 165 passed (102 neu, MockTransport) |
| 3 | `feature/telemetry` | `5c06127` (Code+Report, 1 Commit) | **nur** `app/integrations/{__init__,monitoring,pihole,docker,tailscale,truenas}/**`, `tests/integrations/**`, Doku | 173 passed (110 neu, Fixtures) |
| 4 | `feature/frontend` | `c37c3c0` (Code), `58899ef` (Report) | **nur** `frontend/**` (inkl. `package-lock.json`, `generated/schema.ts` regeneriert) + Doku | tsc 0, eslint 0, vitest 94, build ok (Node 22.14) |
| 5 | `feature/qa` | `7a8b3a9` (Code), `b1a2a58` (Report) | `tests/**` (root), `scripts/qa/**`, `.github/workflows/qa.yml`, `deploy/systemd/{hcc-api.service,health-probe.sh}`, `scripts/deploy-lxc.sh`, **`frontend/eslint.config.js`, `frontend/src/api/client.test.ts`** (QA-Befunde), `docs/quality/**` | Pipeline 12/12 Gates grün (Windows, Exit 0); QA-Suite 118 passed |

## 3. Dateibesitz-Abgleich gegen PARALLEL_WORKFLOW / architecture.md

| Agent | Vorgesehener Besitz | Tatsächlich | Abweichung |
| --- | --- | --- | --- |
| 1 backend-auth | `app/auth/**`, `app/users/**`, `tests/auth/**` | + `app/actions/**` (neu), `app/api/v1/{auth,health,integrations}.py`, `app/audit/log.py`, `app/errors.py`, `app/logging_setup.py`, `app/__init__.py`, weitere `tests/*` | **Ja, dokumentiert** im R1-backend-Report (§2): Core-Hardening laut agent-tasks/01 (Rate-Limiting, Audit-Hooks, Error-Format, PG-Verifikation). Keine Berührung von `contracts/**`, `alembic/**`. |
| 2 frontend | `pages/ components/ features/ styles/` | + `src/api/**` (client, query, types, fixtures, generated), `src/lib/**`, `index.html`, `package.json`, `vite.config.ts`, `eslint.config.js` | **Ja, dokumentiert**: `api/client.ts` war R0-Shell (Agent 2 soll sie laut Handoff §6.3 ausbauen); `generated/` nur per `gen:types` regeneriert (identisch zum frozen Contract). |
| 3 proxmox | `integrations/proxmox/**`, `inventory/proxmox/**`, `tests/proxmox/**` | exakt wie vorgesehen | Nein |
| 4 telemetry | `integrations/monitoring/**, pihole/**, truenas/**, tailscale/**, docker/**`, `tests/integrations/**` | + `integrations/__init__.py` (guarded Imports) | **Ja, dokumentiert**: Package-Init für App-Wiring, nur eigene Subpackages, guarded. |
| 5 qa-security | `tests/e2e/**`, `tests/security/**`, `scripts/qa/**`, `docs/quality/**` | + `tests/contract/**`, `tests/{pytest.ini,conftest.py,__init__.py}`, `.github/`, `deploy/**`, `scripts/deploy-lxc.sh`, **2 Frontend-Dateien** | **Ja, dokumentiert** im R1-qa-Report (§3): Deploy-Artefakt-Härtung (Mandat "Deployment-Review + Härtung") und 2 QA-Befunde in Frontend-Dateien (Lint-Config + 1 Testdatei, keine Produktlogik). |

**Wichtig:** Kein Branch hat `backend/app/contracts/**`, `backend/contracts/openapi.v1.json`,
`backend/alembic/**` oder globale Dependencies (`backend/pyproject.toml`) geändert.
Kein Branch hat `master` oder einen anderen Feature-Branch angefasst.

## 4. Abhängigkeiten und Konfliktrisiken

### 4.1 Dateiebene (Merge-Konflikt-Potenzial)

| Merge (Reihenfolge) | Gemeinsame Dateien | Risiko |
| --- | --- | --- |
| 1: `feature/auth` | keine (alle anderen Branches berühren diese Dateien nicht) | niedrig |
| 2: `feature/proxmox` | keine | niedrig |
| 3: `feature/telemetry` | `backend/app/integrations/__init__.py` (neu, Agent 4) vs. `backend/app/integrations/proxmox/` (neu, Agent 3) — keine gemeinsame Datei, nur gleiches Verzeichnis | niedrig |
| 4: `feature/frontend` | keine (Backend-/QA-Branches berühren `frontend/` nicht außer QA, das kommt als 5.) | niedrig |
| 5: `feature/qa` | **`frontend/src/api/client.test.ts`** (QA + Frontend haben beide gegenüber R0 die CSRF-POST-Testgruppe umgeschrieben) und **`frontend/eslint.config.js`** (beide fügen `tseslint` ein, beide ändern den Vitest-Globals-Block) | **hoch** — inhaltliche Kollision, semantisch auflösen (siehe §4.5) |

`scripts/deploy-lxc.sh` und `deploy/systemd/hcc-api.service` werden nur von QA geändert → kein Konflikt.

### 4.2 Laufzeit-/Testebene (keine Dateikollision, aber Wechselwirkung)

| # | Wechselwirkung | Betroffen | Gegenmaßnahme |
| --- | --- | --- | --- |
| A1 | **Registry-Vorbelegung:** `app/integrations/__init__.py` (Agent 4) registriert 5 Adapter beim Paket-Import; Proxmox-Adapter wird nirgends registriert (bewusst, Agent 3 — Core-Hook fehlt, Proposal `agent3-proxmox-core-integration.md` Item 1). R0-Test `test_adapter_interface.py` registriert `FakeAdapter(PROXMOX)` **ohne** Registry-Reset. | `verify`-E2E bleibt in Produktion `not_implemented` für alle Adapter; R0-Test bricht, sobald ein Core-Registrierungs-Hook (`create_app`) eingeführt wird | Integrationsfix: Bootstrap-Hook `register_all_adapters()` (Core, dokumentierter Agent-3-Vorschlag) + R0-Test-Fixture erhält `_reset_for_tests()` vor dem Register (identisches Muster wie `tests/proxmox/conftest.py`) |
| A2 | **Modul-globaler `_bootstrap_limiter`** (feature/auth, 5/60s pro IP): `backend/tests/conftest.py` (Agent 1) resettet beide Limiter; **`tests/conftest.py` (QA, root) resettet nur `_login_limiter`** (auf R0-Code geschrieben). QA-Suite bootstrapped pro Test → ab 6. Bootstrap im 60s-Fenster → 429 → QA-Tests rot. | QA-Suite nach Merge 1+5 | Integrationsfix: `tests/conftest.py::_reset_rate_limiter` um `_bootstrap_limiter` erweitern (kein Produkt-Code, kein Semantik-Change) |
| A3 | **Login inaktiver User:** feature/auth liefert bei Login deaktivierter User **403** (`Konto ist deaktiviert`), laufende Sessions erhalten 401 (Session-Check). QA-Test "Deaktivierter User: laufende Session → 401" bleibt konsistent; QA-Auth-Tests mit Login-Versuch deaktivierten Users wären sonst inkonsistent. | QA `test_auth_hardening`/`test_session_security` | Nach Merge 1+5 Suite laufen lassen; ggf. QA-Test an reales (getestetes) Backend-Verhalten anpassen — nur falls tatsächlich rot, ohne Semantik-Änderung |
| A4 | **OpenAPI-Snapshot:** alle 5 Branches berichten "Snapshot grün/unchanged". Jeder Merge wird mit `test_contracts_snapshot.py` + `check_openapi_drift.py` verifiziert. | Contract-Stabilität | Gate nach jedem Merge |
| A5 | **`backend/tests/test_postgresql.py`** (Agent 1): Offline-DDL-Rendering via tmp-`env.py` (Wechselarbeit für den dokumentierten Alembic-Offline-Defekt, Proposal `backend-alembic-offline-sql.md`). | Windows-Kompatibilität des tmp-Env-Ansatzes | Nach Merge 1 laufen lassen |
| A6 | **Untracked `frontend/package-lock.json` in `hcc-qa`** (R6): Merge-Funktion nicht betroffen (untracked); Frontend-Branch commitet eigenes Lockfile → integriert. QA-Lokalkopie bleibt untracked im QA-Worktree (nicht mein File, nicht committen). | Reproducibility | Kein Handlungsbedarf im Integrationsbranch |

### 4.3 Contract-/Proposal-Lage (alle "offen" → blockiert, nicht implementiert)

| Proposal | Agent | Status in R1 |
| --- | --- | --- |
| `backend-auth-change-password.md` | 1 | offen → Passwortwechsel-API blockiert (Service fertig/getestet) |
| `backend-errors-method-not-allowed.md` | 1 | offen → 405 bleibt frozen `not_found` |
| `backend-alembic-offline-sql.md` | 1 | offen → Offline-DDL nur via Test-Workaround (Fix ist Shared-Bereich `alembic/env.py`) |
| `agent3-proxmox-core-integration.md` | 3 | Item 1 (Bootstrap-Hook) = **Integrationsfix R1** (kein Contract-Change); Items 2–4 = R2 (sync/actions-Endpoints, options-Spalte) |
| `agent4-monitoring-api.md` | 4 | offen → keine REST-Endpunkte für discover/metrics/events; Event-Store blockiert |
| `frontend-vm-actions.md` | 2 | offen → UI ehrlich "blockiert" |
| `frontend-metrics-and-alerts.md` | 2 | offen → Monitoring-Page zeigt "nicht verfügbar" |
| `frontend-topology-bulk-relations.md` | 2 | offen → Topologie limitiert 200 |
| `frontend-password-change.md` | 2 | offen → Settings zeigt "erforderlich/blocked" |

**Keine Contract-Änderung ist in R1 nötig.** Die einzige Core-Änderung
(Adapter-Bootstrap-Hook in `main.py`/`integrations/bootstrap.py`) ist ein
dokumentierter Agent-3-Vorschlag, ändert weder OpenAPI-Snapshot noch
Migrationen und wird im Release-Report explizit genannt.

### 4.4 GEMEINSAME R0-FOUNDATION (Basis aller Branches)

- `c86c3a4` enthält: frozen Contracts + OpenAPI-Snapshot (15 Pfade),
  Auth/RBAC/CSRF/Audit, Adapter-Interface (leere Registry),
  Alembic `0001_initial`, Deployment-Skripte, Frontend-R0-Shell.
- Alle Feature-Branches wurden gegen diese Basis gebaut; R0-Suite (63 Tests)
  bleibt in jedem einzelnen Branch grün (laut Reports + eigener Baseline-Lauf).

### 4.5 Konflikt-Auflösungsplan (Merge 5, QA)

- `frontend/src/api/client.test.ts`: Merged-Client (`client.ts` aus Frontend-Branch)
  setzt `Content-Type: application/json` **nur mit Body**. Finale Testmenge =
  Union beider Absichten, konsistent mit dem merged Client:
  (1) POST mit Body → CSRF + Content-Type, (2) POST ohne Body → CSRF, **kein**
  Content-Type (QA-Befund S7), (3) PUT mit Body → Content-Type (Frontend),
  (4) GET ohne CSRF, (5) Error-Envelope-Tests (R0, unverändert), (6) `buildQuery`
  (Frontend). Keine Test-Deaktivierung.
- `frontend/eslint.config.js`: Union = `tseslint.configs.recommended` (beide),
  Vitest-Globals `files` inkl. `**/*.test.{ts,tsx}` **und** `vitest.setup.ts` (QA),
  Globals inkl. `vi` (Frontend) + `globals.jest`, React-Regeln (Frontend).
  Danach `npx eslint .` + `npx vitest run` auf dem Integrationsbranch.

## 5. Umgebung (Entwicklungsmaschine, Windows) — für Phase C relevant

| Tool | Status |
| --- | --- |
| uv 0.11.7 / Python 3.14.4 | ✓ (Backend, `backend/.venv` vorhanden, dev-Extra ok) |
| Node 22.23.4 (portabel, aus `hcc-qa/tools/`) | ✓ (Frontend-Gates) |
| PostgreSQL-Server | **✗** (kein Service, kein Programm, kein Docker, kein WSL) → Live-Migration nicht auf dieser Maschine ausführbar → explizit als "nicht durchgeführt" dokumentiert; Offline-DDL-Tests (Agent 1) als Evidenz |
| Bash (Linux) / Git-Bash / WSL | **✗** (nur `C:\Windows\system32\bash.exe`-Stub) → `run-qa.sh`, `deploy-lxc.sh`-Runtime, `e2e-smoke.sh` **nicht ausführbar** → Linux-spezifisch, als nicht durchgeführt dokumentiert (statischer `bash -n`/Review nur) |
| Reale Integrationssysteme (Proxmox, Prometheus, …) | **✗** nicht erreichbar — Mock-/Fixture-Tests nur (klar gekennzeichnet) |
