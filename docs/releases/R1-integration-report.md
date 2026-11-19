# R1 — Integrations- & Release-Report

**Stand:** 2026-11-11 · **Integrationsbranch:** `integration/r1`
**Autor:** Integrations-/Release-Engineering (R1)
**Basis:** `c86c3a4` (`master`, R0 Foundation + Handoff)
**Zugehörig:** `docs/releases/R1-integration-matrix.md` (Preflight, Commit `b05a224`)

---

## 1. Zusammenfassung & Verdict

Alle fünf fertigen Feature-Branches (`feature/auth`, `feature/proxmox`,
`feature/telemetry`, `feature/frontend`, `feature/qa`) wurden in der
vorgeschriebenen Reihenfolge mit `--no-ff` auf `integration/r1` gemergt.
Die Systemvalidierung (Phase C) ist auf dem integrierten Tree **vollständig
grün**: Backend 337 passed / 1 skipped, QA-Root-Suite 118/118, Frontend
tsc/eslint/vitest/build grün, OpenAPI-Contract unverändert, 12-Gate-QA-
Pipeline durchgelaufen. Vier Integrationsfehler (Registry-Bootstrap,
QA-Bootstrap-Limiter, 2 veraltete Test-Prämisse, Secret-Scan-Kollision)
wurden identifiziert und behoben — ohne Test-Deaktivierung, ohne
Contract-Änderung, ohne Sicherheitsumgehung. Das Deployment wurde nur
**statisch** reviewed; kein Deployment, kein Push, kein Merge nach
`master` wurde ausgeführt.

**Verdict: `integration/r1` ist release-ready für die Freigabe zum Merge
nach `master`** (Entscheidung des Auftraggebers). Bekannte, dokumentierte
Offenheiten: S1/S3 (R0-Security-Findings, R2-Kandidaten), Live-
PostgreSQL-Migration nicht auf der Dev-Maschine ausführbar (Offline-DDL
als Evidenz), Linux-spezifische Skripte nur statisch geprüft.

**Integrations-Commits auf `integration/r1`:**

| Commit | Inhalt |
| --- | --- |
| `db55030` | Merge 1: `feature/auth` (Agent 1) |
| `a9975cc` | Merge 2: `feature/proxmox` (Agent 3) |
| `b9b05e4` | Merge 3: `feature/telemetry` (Agent 4) |
| `0719a52` | Merge 4: `feature/frontend` (Agent 2) |
| `ff2da9d` | Merge 5: `feature/qa` (Agent 5, 2 Konflikte semantisch gelöst) |
| `b05a224` | `docs/releases/R1-integration-matrix.md` (Preflight-Lieferung) |
| `e46bb31` | Phase-E-Fixes: Adapter-Bootstrap + QA-Limiter + Test-Prämissen (7 Dateien) |
| `24717db` | Secret-Scan-Allowlist mit 8 dokumentierten R1-Freigaben |

---

## 2. Phase A — Preflight & Integrationsmatrix

- Alle Pflichtdokumente gelesen: `MASTER_PROMPT.md`, `agent-tasks/01–05`,
  `docs/PARALLEL_WORKFLOW.md`, `docs/architecture.md`, `docs/api-contracts.md`,
  `docs/foundation-handoff.md`, 5 Agent-Reports, 7 Proposals,
  `docs/quality/security-findings.md` (S1–S10),
  `docs/quality/deployment-review.md`.
- Git verifiziert: alle fünf Feature-Branches basieren auf `c86c3a4`
  (`master`), **keine Kreuz-Merges**, keine veränderter `master`; alle
  Worktrees clean (einzige Ausnahme: untracked `frontend/package-lock.json`
  im QA-Worktree — bekannt, kein Handlungsbedarf, da der Frontend-Branch
  ein eigenes Lockfile committet, §7/S9).
- R0-Baseline vor dem ersten Merge: `uv run --extra dev pytest -q` →
  **63 passed** (alle grün).
- Ergebnis: `docs/releases/R1-integration-matrix.md` (Commit `b05a224`) —
  Dateibesitz-Abgleich, Konflikt-Risiken (A1–A6), Konflikt-Auflösungsplan
  für Merge 5, Umgebungsbestandsaufnahme.

---

## 3. Phase B — Merge-Sequenz

Reihenfolge exakt eingehalten: **auth → proxmox → telemetry → frontend → qa**,
jeweils `git merge --no-ff` auf `integration/r1`.

| # | Branch | Merge-Commit | Konflikte | Ergebnis nach Merge |
| --- | --- | --- | --- | --- |
| 1 | `feature/auth` | `db55030` | keine | Backend-Suite grün, Snapshot grün |
| 2 | `feature/proxmox` | `a9975cc` | keine | Backend-Suite grün, Snapshot grün |
| 3 | `feature/telemetry` | `b9b05e4` | keine | Backend-Suite grün, Snapshot grün |
| 4 | `feature/frontend` | `0719a52` | keine | Frontend-Gates grün, Snapshot grün |
| 5 | `feature/qa` | `ff2da9d` | **2** | Frontend-Gates grün, Snapshot grün |

**Konflikt-Auflösung Merge 5** (laut Matrix-Plan §4.5, semantisch, keine
Test-Deaktivierung):
- `frontend/src/api/client.test.ts`: Union beider Test-Absichten, konsistent
  mit dem mergeden Client (`Content-Type` nur mit Body — QA-Befund S7).
- `frontend/eslint.config.js`: Union `tseslint.configs.recommended`,
  Vitest-Globals-Block inkl. `vitest.setup.ts` (QA) und `vi`
  (Frontend), React-Regeln.
- Sofort-Vergleich nach Merge 5: `npx tsc -b --noEmit` (0 Fehler),
  `npm run lint` (0 Fehler), `npx vitest run` (95/95), `npm run build` (ok).

**Wichtig:** Bei keinem Merge wurden Agent-Änderungen ungeprüft
überschrieben; alle Konflikte wurden semantisch aufgelöst und mit den
Gates des betroffenen Bereichs verifiziert.

---

## 4. Phase C — Systemvalidierung: Test-Evidenz

Alle Läufe auf dem integrierten Tree (`integration/r1`) nach Abschluss
aller Fixes. Befehle:

| Gate | Befehl | Ergebnis |
| --- | --- | --- |
| Backend-Unit-Tests | `cd backend; uv run --extra dev pytest -q` | **337 passed, 1 skipped** (57.9 s) |
| Backend-Lint | `uv run --extra dev ruff check .` | **All checks passed** |
| OpenAPI-Snapshot | `pytest tests/test_contracts_snapshot.py` | **4/4 passed** |
| OpenAPI-Drift | `scripts/qa/check_openapi_drift.py` | **OK (Gate grün)** |
| Migrationstests (offline) | in Backend-Suite: `tests/test_migration.py`, `tests/test_health_migration.py`, `tests/test_postgresql.py` (Offline-DDL) | **grün** (Teil der 337) |
| QA-Root-Suite | `uv run --project backend python -m pytest tests -q` | **118/118 passed** |
| Frontend-Typecheck | `npx tsc -b --noEmit` | **0 Fehler** |
| Frontend-Lint | `npm run lint` | **0 Fehler** |
| Frontend-Tests | `npx vitest run` | **95/95 passed** |
| Frontend-Build | `npm run build` (Vite, Produktions-Build) | **ok** |
| 12-Gate-Pipeline | `powershell -ExecutionPolicy Bypass -File scripts/qa/run-qa.ps1` (Node via `HCC_NODE_BIN` = portabler Node 22.23.4 aus `hcc-qa/tools/`) | s. unten |

**12-Gate-Pipeline-Ergebnis (`run-qa.ps1`):**

| Gate | Ergebnis |
| --- | --- |
| 1. Secret-Scan | OK (nach dokumentierter Allowlist-Erweiterung, §8) |
| 2. Backend-Lint (ruff) | OK |
| 3. Backend-Unit-Tests (pytest) | OK |
| 4. OpenAPI-Drift (Contract-Snapshot) | OK |
| 5. QA-Suite (pytest tests/) | OK |
| 6. Frontend-Typecheck (tsc) | OK |
| 7. Frontend-Build (vite) | OK |
| 8. Frontend-Tests (vitest) | OK |
| 9. Frontend-Lint (eslint) | OK |
| 10. Dependency-Audit (Python, `uv audit`) | OK (keine Vulnerabilities) |
| 11. Dependency-Audit (npm, prod-Abhängigkeiten) | OK (keine Vulnerabilities) |
| 12. Deploy-Invarianten (systemd/nginx/deploy-lxc.sh) | OK |

**Der einzige Skip** ist `backend/tests/test_postgresql.py::
test_postgresql_live_migration_roundtrip` (`skipif`: `HCC_TEST_DATABASE_URL`
nicht gesetzt) — bewusst keine Live-Migration in dieser Umgebung, s. §10.

**QA-Root-Suite-Aufschlüsselung (118):** `tests/contract/test_openapi_
contract.py` 19 · `tests/security/test_auth_hardening.py` 5 ·
`test_csrf_matrix.py` 22 · `test_input_validation.py` 21 ·
`test_rbac_matrix.py` 36 · `test_secret_leakage.py` 7 ·
`test_session_security.py` 8.

**R0-Nachholpflichten:**
- **Frontend-Build:** erfüllt — Produktions-Build (`vite build`) auf dem
  integrierten Tree erfolgreich ausgeführt (Gate 7).
- **PostgreSQL-Live-Migration:** nicht auf der Dev-Maschine ausführbar
  (kein PG-Server/Docker/WSL) → in §10 als „nicht durchgeführt"
  dokumentiert; Evidenz = Offline-DDL-Tests (Agent 1) + Alembic-
  Upgrade/Downgrade auf SQLite (grün, Teil der 337).

---

## 5. Phase C — E2E-Flow-Abdeckung

E2E-Flows laufen als TestClient-basierte Full-Stack-Tests gegen die echte
FastAPI-App (RBAC, CSRF, Sessions, Error-Handling echt) — reale
Integrationssysteme sind auf der Dev-Maschine nicht erreichbar und werden
mit klar gekennzeichneten Mock-Servern/Fixtures getestet.

| E2E-Flow | Abdeckung (Datei) | Typ |
| --- | --- | --- |
| Login/Logout | `backend/tests/auth/test_login.py`, `test_password_change.py`; `tests/security/test_auth_hardening.py`, `test_session_security.py` | Full-Stack (TestClient) |
| RBAC/CSRF | `backend/tests/auth/test_rbac.py`, `test_rbac_matrix.py`, `test_csrf.py`; `tests/security/test_rbac_matrix.py` (36), `test_csrf_matrix.py` (22), `test_input_validation.py` (21) | Full-Stack (TestClient) |
| Integrationsverwaltung | `backend/tests/test_integrations_r1.py`, `test_integration_bootstrap.py` (4, neu), `tests/contract/test_openapi_contract.py` | Full-Stack (TestClient) |
| Proxmox Discovery | `backend/tests/proxmox/test_discovery.py`, `test_adapter.py`, `test_client.py` | Mock-Server (`tests/proxmox/fixtures/server.py`) |
| Inventar-Sync | `backend/tests/proxmox/test_inventory.py` | Mock-Server |
| Compute-Management (start/shutdown/reboot) | `backend/tests/actions/test_action_service.py` (15), `backend/tests/proxmox/test_actions.py`; Frontend: `features/compute/*.test.tsx` | Mock-Server + RBAC/Audit-Pfad |
| Topologie | Frontend `features/topology/model.test.ts` (React-Flow-Modell) + Backend-Inventar-Tests (Ressourcen/Relations) | Unit + Mock |
| Monitoring | `backend/tests/integrations/test_monitoring_backends.py`, `test_prometheus.py`, `test_pihole.py`, `test_docker.py`, `test_tailscale.py`, `test_truenas.py`, `test_registry_wiring.py` | Fixtures (klar gekennzeichnet) |
| Alerts/Events | `backend/tests/integrations/test_events.py` (Fingerprint/Dedup/Normalisierung), `test_monitoring_backends.py` | Fixtures |
| Fehlerbehandlung | `backend/tests/test_error_envelope.py`, `test_error_handling_r1.py`; `tests/security/test_secret_leakage.py` (keine Secret-Leaks in Fehlermeldungen) | Full-Stack (TestClient) |

Lückenhinweis: `tests/e2e/e2e-smoke.sh` (Produktionspfad über nginx im
Ziel-LXC) ist **nicht** auf dieser Maschine ausführbar (nur
system32-bash-Stub, kein Git-Bash/WSL) → s. §10; Ersatz-Evidenz ist die
TestClient-basierte Full-Stack-Abdeckung oben.

---

## 6. Integrationsfehler & Fixes (Phase E)

Alle Fixes sind committet (`e46bb31` bzw. `24717db`), getestet und
ohne Semantik-Change. Betroffene Dateien:

| # | Fehler | Ursache (Merge-Wechselwirkung) | Fix |
| --- | --- | --- | --- |
| E1 | Verify-Endpunkt antwortete für **alle** Adapter `not_implemented`, weil die Registry nie vorbefüllt wurde (R0-Verhalten) | Agent 3-Proxmox-Adapter registriert sich bewusst nicht selbst; Agent-4-Adapter nur via Import-Side-Effect; kein Core-Hook | `backend/app/integrations/bootstrap.py` (neu): `register_all_adapters()` — Agent-4-Adapter **explizit** pro-Adapter isolated und kollisionsfrei, Proxmox via `register_proxmox_adapter()`; Hook in `create_app()` (`app/main.py`). Impl. von `docs/proposals/agent3-proxmox-core-integration.md` Item 1. 4 neue Tests (`tests/test_integration_bootstrap.py`) |
| E2 | QA-Root-Suite ab 6. Bootstrap im 60-s-Fenster mit 429 (viele rote Tests) | feature/auth führt modul-globalen `_bootstrap_limiter` (5/60s/IP) ein; QA-`tests/conftest.py` resettete nur `_login_limiter` | `tests/conftest.py::_reset_rate_limiter` um `_bootstrap_limiter.reset()` erweitert (Testinfrastruktur, kein Produkt-Code). Suite: von vielen 429-Errors auf **118/118 grün** |
| E3 | 2 Tests gingen rot: Prämisse „tailscale ist nicht implementiert" gilt in R1 nicht mehr (Adapter ist eingebaut) | Agent 4 liefert `tailscale`-Adapter; Tests erwarteten `not_implemented` | Semantische Anpassung: Tests nutzen `homeassistant` — das ehrliche „nicht implementiert"-Kind in R1 (Agent-4-Report Pkt. 4); Test-Intent (keine Registrierung → `not_implemented`) bleibt erhalten. Betroffen: `tests/proxmox/test_adapter.py::test_verify_endpoint_unknown_adapter_is_not_implemented`, `backend/tests/test_integrations_r1.py::test_verify_sets_last_verified_at_even_without_adapter` |
| E4 | R0-Fixture `FakeAdapter` kollidierte mit der neuen `create_app()`-Vorbelegung | Registry wird jetzt von `create_app()` befüllt | `backend/tests/test_adapter_interface.py`: Fixture startet mit `registry._reset_for_tests()` vor dem Register (identisch zu `tests/proxmox/conftest.py`) |
| E5 | Ruff `I001` in `app/main.py` nach Hook-Einfügung | Import-Reihenfolge | Importsortierung korrigiert (Ruff clean) |
| E6 | Secret-Scan: 19 Befunde auf dem integrierten Tree (Gate rot) | QA-Scanner (auf feature/qa gebaut) trifft neue Test-Fixtures von Agent 1/3 und Docstrings/Annotations von Agent 3 — keine echten Secrets | 8 dokumentierte Allowlist-Einträge in `scripts/qa/scan_secrets.py` (das vom Scanner selbst vorgesehene Falsch-Positiv-Verfahren, s. S10), Scan danach **0 Befunde** |

**Bewusst nicht geändert (Scope):** keine Contract-, keine
Alembic-, keine pyproject-/Dependencies-Änderung; keine Test-Deaktivierung;
keine Sicherheitskontrolle umgangen.

---

## 7. Contract-Status & Proposals

- **`backend/contracts/openapi.v1.json` (frozen R0-Contract): unverändert.**
  Snapshot-Test (4/4) und Drift-Check (Gate 4) grün — nach jedem
  Zwischenschritt (nach jedem Merge und nach allen Phase-E-Fixes).
- **Keine der 5 Branches** hat `contracts/**`, `alembic/**`,
  `pyproject.toml` oder globale Dependencies geändert (Matrix §3).
- **Alle 7 Proposals bleiben Status „offen"** → die jeweiligen Features
  sind in R1 blockiert; die UI zeigt sie ehrlich als
  „nicht verfügbar/blockiert" (keine Stubs):
  - `backend-auth-change-password.md` → Passwortwechsel-API blockiert
  - `backend-errors-method-not-allowed.md` → 405 bleibt frozen `not_found`
  - `backend-alembic-offline-sql.md` → Offline-DDL-Defekt via Test-Workaround
  - `agent3-proxmox-core-integration.md` → **Item 1 umgesetzt (E1)**;
    Items 2–4 (sync/actions-Endpoints, options-Spalte) = R2
  - `agent4-monitoring-api.md` → keine Monitoring-REST-Endpunkte
  - `frontend-vm-actions.md` / `frontend-metrics-and-alerts.md` /
    `frontend-topology-bulk-relations.md` / `frontend-password-change.md`
    → UI ehrlich blockiert/limitiert
- S9 (`package-lock.json` fehlt) ist **in R1 gelöst**: der Frontend-Branch
  committet `frontend/package-lock.json` (Commit `c37c3c0`); das Lockfile
  ist auf `integration/r1` tracked.

---

## 8. Security: Secret-Scan, Dependency-Audits, Findings S1–S10

**Secret-Scan (`scripts/qa/scan_secrets.py`, Gate 1):**
Erster Lauf auf dem integrierten Tree: **19 Befunde** — vollständige
Einzelbewertung:

| Kategorie | Befunde | Bewertung |
| --- | --- | --- |
| Test-Passwörter (klar als Fixture markiert, paare Test-User-Namen) | `deactivate-pass-123` (tests/auth/test_auth_hardening.py), `alt-passwort-123` (tests/auth/test_password_change.py) | keine echten Secrets |
| Deterministische Fake-Hex-Tokens für PVEAPIToken-Parse-/Leakage-Tests gegen den lokalen Mock-Server | `0123456789abcdef01234789abcdef012345` (proxmox conftest/test_config/fixtures), `ffff…` (test_client/test_adapter), `0000…` (test_discovery, „bewusst falscher Token") | keine echten Secrets |
| Muster-Falsch-Positive in Produktcode (keine Literale) | `ProxmoxToken` (Typ-Annotation, proxmox/client.py), `_split_token` (Tuple-Unpacking, proxmox/config.py), `user:pass@` (Docstring-Beispiel, monitoring/httputil.py), Docstring-Beispiel-Token (proxmox/config.py) | keine echten Secrets |

Kein einziger Befund ist ein echtes Secret. Aufräumdurchführung nach dem
vom Scanner selbst dokumentierten Verfahren (S10: „Freigabe in der
ALLOWLIST mit Begründung dokumentieren — nie still ignorieren"):
**8 Allowlist-Einträge** mit je konkreter Begründung
(`scripts/qa/scan_secrets.py`). Der Scanner bleibt voll funktionsfähig —
ein reales (anderes) Secret würde weiterhin gemeldet. Ergebnis nach Fix:
**0 Befunde, Gate grün.**

**Dependency-Audits (Gate 10/11):** `uv audit --project backend` → 0
Vulnerabilities (Gate OK); `npm audit --omit=dev` → 0 Vulnerabilities
(Gate OK).

**Security-Findings S1–S10** (QA, aus R0-Code; QA hat R1-Produktcode
bewusst nicht geändert):

| ID | Severity | Status in R1 |
| --- | --- | --- |
| S1 (Audit-FK null bei neuer Integration) | mittel | bekannt, offen — R2-Kandidat (kein Integrationsfehler) |
| S2 (405 als `not_found` statt `method_not_allowed`) | niedrig | bekannt, offen — frozen per Proposal `backend-errors-method-not-allowed.md` |
| S3 (Login-Rate-Limit: 1 Bucket hinter Proxy) | mittel | bekannt, offen — R2-Kandidat; Deployment-Review D6 verweist darauf |
| S4 (`resolve()` prüft `is_active` nicht) | niedrig | abgemildert (RBAC-Schicht prüft); Defense-in-Depth für R2 |
| S5 (LIKE-Wildcards in Suchfiltern) | niedrig | bekannt, offen — parameterisiert, kein SQLi |
| S6 (ESLint-9-Deprecation) | info | dokumentiert |
| S7 (POST ohne Body ohne Content-Type) | info | dokumentiertes Verhalten |
| S8 (TestClient per-Request-Cookies) | info | Test-Tooling, Fixture-Muster beibehalten |
| S9 (kein `package-lock.json`) | niedrig | **in R1 gelöst** (Lockfile committet, `c37c3c0`) |
| S10 (Secret-Scanner als Gate) | info | läuft als Gate 1; R1-Ergebnis s. oben |

Keine Findung mit aktivem Exploit-Pfad (QA-Bewertung); keine wurde in R1
„weg-gepatcht" — alle bleiben in der Doku als Prioritätsgrundlage für R2.

---

## 9. Phase D — Deployment-Review (statisch)

**Kein Deployment ausgeführt** (LXC nicht in Scope von R1). Statische
Prüfung der Artefakte gegen `docs/DEPLOYMENT_PLAYBOOK.md` §5/6:
`deploy/systemd/hcc-api.service`, `deploy/nginx/hcc.conf`,
`deploy/systemd/health-probe.sh`, `scripts/deploy-lxc.sh`. Zusätzlich
automatisches Gate 12 (`scripts/qa/check_deploy_artifacts.py`) → **OK**.

Bestätigte Invarianten:
- **systemd:** `User=hcc`/`Group=hcc` (unprivilegiert), `ExecStart` bindet
  nur `127.0.0.1:8000`, `ExecStartPre=alembic upgrade head`,
  `ExecStartPost` = Health-Probe (Start zählt erst bei `health/live` 200,
  30 s Polling), `TimeoutStartSec=180`, `Restart=on-failure`,
  `EnvironmentFile=/etc/hcc/hcc.env` (+ optionales `secrets.env`),
  Hardening-Block (NoNewPrivileges, PrivateTmp, ProtectSystem=full,
  ProtectHome, …), **kein** Docker-Socket-Bezug.
- **nginx:** nur `listen 127.0.0.1:8080`, Proxy nur an Upstream
  `127.0.0.1:8000`, `server_tokens off`, Sicherheits-Header
  (nosniff/DENY/no-referrer), SSE-Readiness (`proxy_buffering off`,
  120 s Read-Timeout), SPA-Root `/opt/hcc/current/frontend/dist`.
- **Peer-Auth/PG:** dedizierte Rolle `hcc` (kein Superuser), Passwort
  lokal generiert (`openssl rand -hex 24`) in `/etc/hcc/.pg_password`
  (0600 root); psql-Prüfungen via `su - postgres` (Peer-Auth); PG bleibt
  an lokalem Socket/Loopback.
- **Secrets/Rechte:** `hcc.env` 0640 root:hcc, Bootstrap-Token einmalig
  per `openssl rand -hex 24` (kein Literal im Repo), `.env.example` ohne
  Secrets.
- **Idempotenz/Atomarität:** jede Stufe guardet (`if ! id -u hcc`,
  `if [ ! -d "$RELEASE_DIR" ]`, …); `current`-Symlink atomar
  (tmp + `mv`); `git archive HEAD` deployt den kommittierten Stand,
  dirty Worktree → Warnung.
- **Rollback:** `--rollback <sha>` verifiziert Ziel-Release, atomarer
  Symlink-Tausch, `systemctl restart` + Health-Probe; `--list` für
  Release-Übersicht.
- **Keine unsicheren Muster:** kein `curl|sh`/`wget|sh`; uv via pip in
  `/opt/hcc/tools/uv`; `nginx -t` vor Reload.

**Eigenständige Befunde der Integrations-Review (keiner blockierend):**

| # | Befund | Bewertung |
| --- | --- | --- |
| D-I1 | `deploy-lxc.sh` nutzt `npm install --no-audit --no-fund` statt `npm ci`; `frontend/package-lock.json` ist inzwischen committet (`c37c3c0`) → `npm ci` wäre die reproduzierbare Wahl im LXC | R2-Verbesserung (kein R1-Defekt, da Lockfile vorhanden und `npm install` es einhält) |
| D-I2 | Kein automatisches DB-Backup (kein pg_dump-Timer) im Deploy-/Betriebspfad; Rollback deckt nur Applikations-State, nicht Daten | Betriebsaufgabe; R2-Kandidat (systemd-Timer + Retention) |
| D-I3 | `After=postgresql.service` ohne `Requires=`: ein PG-Stillstand führt zu 500er aus der App, nicht zu Service-Neustart; Health-Probe feuert nur beim Start | Akzeptabel für Homelab-Scope, dokumentiert; Monitoring/R2-Kandidat |

---

## 10. Nicht durchgeführt / blockiert, Risiken, Integrationshinweise

**Nicht durchgeführt (mit Grund, nicht als „erfolgreich" gemeldet):**

| Test/Step | Grund | Ersatz-Evidenz |
| --- | --- | --- |
| PostgreSQL-**Live**-Migration (`test_postgresql_live_migration_roundtrip`) | Kein PG-Server, kein Docker, kein WSL auf der Dev-Maschine (`HCC_TEST_DATABASE_URL` nicht setzbar) | Offline-DDL-Tests (Agent 1, `tests/test_postgresql.py`), Alembic upgrade/downgrade auf SQLite (grün), `ExecStartPre`-Design im LXC |
| `scripts/qa/run-qa.sh` (Linux-Variante) | Kein Bash/Git-Bash/WSL (nur system32-Stub) | `run-qa.ps1` (Windows-Spiegel, Agent 5) vollständig grün — §4 |
| `scripts/deploy-lxc.sh`-Runtime, `tests/e2e/e2e-smoke.sh` | Linux-spezifisch; Ziel-LXC nicht in R1-Scope | Statische Review (§9) + Gate 12 (Deploy-Invarianten OK) |
| E2E gegen reale Integrationssysteme (Proxmox, Prometheus, …) | Nicht erreichbar von der Dev-Maschine | Mock-Server/Fixtures (klar gekennzeichnet) — §5 |
| Merge nach `master`, `git push`, echtes LXC-Deployment | Aufgaben-Scope: nur `integration/r1`, keine Push/Deployment | — |

**Offene Risiken (konsolidiert):**
- **S1/S3** (Audit-FK, Rate-Limit-Key hinter Proxy): R2-Kandidaten,
  dokumentiert in `docs/quality/security-findings.md`.
- **Bootstrap-Token bleibt nach Nutzung** in `/etc/hcc/hcc.env`
  (Deployment-Review D3): Rotation = Betriebsschritt.
- **OpenAPI-Spec öffentlich** (Deployment-Review D2): bewusster
  Doku-Vertrag, nur Schema ohne Daten.
- **In-memory-Rate-Limits** (Deployment-Review D6 = S3):
  Single-Instance-Annahme, dokumentiert.
- **Live-Migrations-Evidenz fehlt auf Dev-Maschine**: im Ziel-LXC wird
  `alembic upgrade head` als `ExecStartPre` mit Health-Probe-Gate laufen
  (erst danach gilt der Start als erfolgreich).

**Integrationshinweise / nächste Schritte:**
1. **Freigabe durch den Auftraggeber**, dann `master` ← `integration/r1`
   (Merge-Entscheidung liegt bei `master`-Besitz; nicht vom Integrator
   ausgeführt).
2. Nach Merge: im Ziel-LXC `sudo scripts/deploy-lxc.sh <checkout> --start`
   ausführen, anschließend `tests/e2e/e2e-smoke.sh` (Produktionspfad) —
   erst dann als produktiv betrachten (Empfehlung Deployment-Review §6).
3. R2-Kandidaten gesammelt: D-I1 (`npm ci` im LXC), D-I2 (DB-Backup),
   D-I3 (PG-Dependency-Monitoring), S1/S3 (Security), Proposal-Items
   (Agent 3 Items 2–4, Agent-4-Monitoring-API, Frontend-VM-Actions,
   Metrics/Alerts-UI, Topologie-Bulk-Relations, Passwortwechsel-UI,
   `method_not_allowed`, Alembic-Offline-SQL).

**Betroffene Dateien dieses Integrations-Runs (eigene Commits):**
- `docs/releases/R1-integration-matrix.md` (neu, `b05a224`)
- `backend/app/integrations/bootstrap.py` (neu, `e46bb31`)
- `backend/app/main.py` (`e46bb31`)
- `backend/tests/test_integration_bootstrap.py` (neu, `e46bb31`)
- `backend/tests/test_adapter_interface.py` (`e46bb31`)
- `backend/tests/test_integrations_r1.py` (`e46bb31`)
- `backend/tests/proxmox/test_adapter.py` (`e46bb31`)
- `tests/conftest.py` (`e46bb31`)
- `scripts/qa/scan_secrets.py` (Allowlist-Erweiterung, `24717db`)
- `docs/releases/R1-integration-report.md` (neu, dieser Report)

Feature-Branches und `master` sind nicht verändert; alle
Feature-Worktrees bleiben, wie sie die Agenten hinterlassen haben.

---

## 11. Postscript (2026-11-19, nach Freigabe)

- **Freigabe** durch den Auftraggeber; `integration/r1` → `master`
  gemergt (**Fast-forward**, `master`-Tip = `342f3bc` = identischer
  Commit/identischer Tree wie `integration/r1` — daher keine erneute
  Testlauf-Evidenz nötig, alle §4-Ergebnisse gelten unverändert).
- **Push nach `https://github.com/falkinat0r/FMHCC.git`** (Remote
  `origin`): alle 8 Branches — `master` (Default-Branch),
  `integration/r1`, `foundation`, `feature/auth`, `feature/frontend`,
  `feature/proxmox`, `feature/qa`, `feature/telemetry`. Kein Force-Push.
- Restliche Release-Schritte laufen im Ziel-System (nicht in diesem
  Repository): LXC-Deployment + `tests/e2e/e2e-smoke.sh` (s. §10).
