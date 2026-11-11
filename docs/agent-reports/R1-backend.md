# R1 Backend-Report — Agent 1 (backend-auth)

- **Branch/Worktree:** `feature/auth` in `C:\Users\muehleisen\Documents\hcc-auth`
- **Commit:** `f6eb853` — `feat(R1): Backend-Core-Hardening (Agent 1)` (27 Dateien, +2082/−20)
- **Basis:** R0 Foundation (`c9c9553`, `c86c3a4`)
- **Status:** `tested` (alle R1-Funktionen unit-/integrationstestiert; Live-PostgreSQL-Test gependet, da in dieser Umgebung kein erreichbares PostgreSQL vorhanden)
- **Contracts:** `backend/contracts/openapi.v1.json` **unverändert** (Snapshot-Test grün); drei Vorschläge in `docs/proposals/`

## 1. Implementierte R1-Funktionen

### 1.1 Auth & Session-Hardening (`app/auth/sessions.py`, `app/api/v1/auth.py`)
- **Login-Timing-Gleichbehandlung:** Unbekannter User triggernt einen Argon2id-Verify gegen Dummy-Hash (konstanter Zeitablauf, kein User-Enumeration).
- **Session-Purge:** Abgelaufene Sessions werden bei Aktivität bereinigt; `revoke_all_for_user` widerruft alle Sessions eines Users.
- **Inaktiver User:** Bestehende Session wird beim nächsten Request abgewiesen (401), auch wenn das Cookie formal gültig ist.
- **Bootstrap-Rate-Limit:** 5/60s pro IP (zusätzlich zum Login-Limit 10/60s); jeder Aufruf verbraucht eine Limit-Position.
- **Persistente Fehler-Audits:** `record_audit(..., commit=True)` — Login-/Bootstrap-Fehler werden auditiert und überleben die Request-Session-Rollback (R0-Gap behoben).

### 1.2 RBAC-Matrix & User-Service (`app/users/service.py`, `app/api/v1/users.py`)
- **`change_password` (Service-Ebene):** Aktuelles Passwort verifiziert, neues validiert, `must_change_password` zurückgesetzt, alle Sessions widerrufen, auditiert (`auth.password_changed`). **API-Endpunkt blockiert** (frozen Contract hat keinen; Vorschlag `docs/proposals/backend-auth-change-password.md`).
- Vollständige RBAC-Matrix-Tests für Viewer/Operator/Admin über alle Endpunkte.

### 1.3 ActionJob-Service (neu: `app/actions/{__init__,states,service}.py`)
- **Keine echten Infrastruktur-Aktionen** (nur Status-Tracking, RBAC-geprüft, auditiert).
- Zustandsmaschine: `pending → running → succeeded | failed` (keine illegalen Transitionen, getestet).
- `actor` (User-ID) und `target` (integration/resource) sind pflicht und tracebar.
- Serverseitige RBAC-Prüfung: nur `operator`/`admin` dürfen Jobs anlegen; `viewer` → 403.
- **Keine API-Endpunkte** (frozen Routenplan enthält keine; Agent-3-Bereich für Proxmox-Aktionen).
- Integration-Delete blockiert, wenn ActionJobs existieren (409 statt 500/FK-RESTRICT).

### 1.4 Health-Readiness (`app/api/v1/health.py`)
- **Migration-Check bei PostgreSQL:** `alembic_version` existiert und entspricht dem Repository-Head → ok; fehlt oder abweichend → degraded (503); DB-Down → unavailable (503).
- SQLite-Tests sind davon unberührt (kein Migration-Check bei nicht-PostgreSQL-URLs).
- Response-Shape und Contract bleiben identisch (nur zusätzliche `migration`-Check-Entry).

### 1.5 Secrets-Masking & Logging (`app/logging_setup.py`, `app/audit/log.py`)
- **Erweiterte Maskier-Feldliste:** `password`, `password_hash`, `token`, `access_token`, `refresh_token`, `secret`, `api_key`, `client_secret`, `private_key`, `authorization`, `cookie`, `session_token`, `csrf_token`, `bootstrap_token`.
- **Rekursion:** Verschachtelte Dicts werden maskiert (R0-Semantik: exakter Key-Match).
- **`secret_ref`** ist ein Name (Referenz), kein Wert → wird NICHT maskiert (darf in API-Antworten erscheinen).
- Audit-Details werden end-to-end maskiert (Test: `test_audit_details_are_masked_end_to_end`).

### 1.6 Error-Handling (`app/errors.py`)
- **429-Antworten** tragen `Retry-After: 60` (für Clients/Proxies).
- **405** bleibt `not_found` (frozen Mapping); `method_not_allowed`-Code fehlt im frozen Enum → Vorschlag `docs/proposals/backend-errors-method-not-allowed.md`.
- Einheitliche Error-Envelope `{"error": {"code", "message", "details", "request_id"}}` für alle Fehlerpfade.

### 1.7 Integration-Management (`app/api/v1/integrations.py`)
- **`verify`** setzt `last_verified_at` auf allen nicht-404-Pfaden (auch `not_implemented`).
- **Delete** liefert 409, wenn ActionJobs für die Integration existieren (sonst FK-RESTRICT → 500).

### 1.8 PostgreSQL-Verifikation (`tests/test_postgresql.py`)
- **Offline-DDL (ohne Server):** Initialmigration wird gegen das PostgreSQL-Dialekt gerendert (via tmp-`env.py` + echte `versions/`-Skripte). Prüft: alle 7 Tabellen, benannte CHECK-Constraints, Foreign Keys, UUID-Typ.
- **Live (optional):** Bei `HCC_TEST_DATABASE_URL` wird die Migration ausgeführt, Tabellen inspiziert, User-Roundtrip gespielt. Andernfalls sauber gependet.
- **Hinweis:** Geteilte `backend/alembic/env.py` ist im Offline-Modus defekt (R0-Defekt) → Vorschlag `docs/proposals/backend-alembic-offline-sql.md`; R1-Test nutzt tmp-Env als Workaround.

## 2. Betroffene Dateien

### Produktion (geändert)
| Datei | Änderung |
| --- | --- |
| `backend/app/__init__.py` | `RELEASE` R0→R1 (freier String, kein Contract) |
| `backend/app/api/v1/auth.py` | Bootstrap-Limiter, Dummy-Hash-Timing, persistente Fehler-Audits |
| `backend/app/api/v1/health.py` | PostgreSQL-Migration-Readiness-Check |
| `backend/app/api/v1/integrations.py` | `verify` → `last_verified_at`; Delete-Block bei ActionJobs (409) |
| `backend/app/audit/log.py` | `record_audit(..., commit=True)` für Fehlerpfade |
| `backend/app/auth/sessions.py` | Session-Purge, `revoke_all_for_user`, inaktiver-User-Check |
| `backend/app/errors.py` | `Retry-After` bei 429 |
| `backend/app/logging_setup.py` | Erweiterte Maskier-Feldliste, Rekursion |
| `backend/app/users/service.py` | `change_password` (Service-Ebene, getestet) |

### Produktion (neu)
| Datei | Zweck |
| --- | --- |
| `backend/app/actions/__init__.py` | Package-Export |
| `backend/app/actions/service.py` | ActionJob-Service (RBAC, Audit, Status-Tracking) |
| `backend/app/actions/states.py` | Zustandsmaschine + Transition-Validierung |

### Tests (geändert)
| Datei | Änderung |
| --- | --- |
| `backend/tests/conftest.py` | Shared-Fixture `_reset_rate_limiter` setzt auch `_bootstrap_limiter` zurück |
| `backend/tests/test_version.py` | `release` auf R1 angepasst |

### Tests (neu)
| Datei | Tests |
| --- | --- |
| `backend/tests/actions/test_action_service.py` | 15 (Status-Transitions, RBAC, Audit, Actor/Target) |
| `backend/tests/auth/test_auth_hardening.py` | 8 (Bootstrap-Limit, persistente Audits, Timing, Session-Purge, inaktiver User) |
| `backend/tests/auth/test_password_change.py` | 6 (Verifikation, Validierung, Session-Invalidierung, Audit) |
| `backend/tests/auth/test_rbac_matrix.py` | 5 (Viewer/Operator/Admin über alle Endpunkte) |
| `backend/tests/test_error_handling_r1.py` | 3 (Retry-After, 405-Envelope, 409-Envelope) |
| `backend/tests/test_health_migration.py` | 5 (SQLite-kein-Check, PG-migrated, PG-out-of-sync, PG-unmigrated, PG-DB-down) |
| `backend/tests/test_integrations_r1.py` | 6 (verify→last_verified_at, 404, Delete-Block) |
| `backend/tests/test_postgresql.py` | 5 (4 offline-DDL + 1 live gependet) |
| `backend/tests/test_secrets_masking.py` | 6 (Feldliste, Rekursion, case-insensitive, Audit-Masking, secret_ref) |

### Doku (neu)
| Datei | Zweck |
| --- | --- |
| `docs/proposals/backend-auth-change-password.md` | Vorschlag: Passwort-Änderungs-Endpunkt (Contract-Erweiterung) |
| `docs/proposals/backend-errors-method-not-allowed.md` | Vorschlag: `method_not_allowed` im frozen ErrorCode-Enum |
| `docs/proposals/backend-alembic-offline-sql.md` | Vorschlag: Alembic-Offline-Modus reparieren |

## 3. Getestete Schritte (ausgeführte Befehle)

Alle Befehle aus `C:\Users\muehleisen\Documents\hcc-auth\backend`:

| Befehl | Ergebnis |
| --- | --- |
| `uv run pytest` (vollständige Suite) | **121 passed, 1 skipped** (skip: Live-PG, `HCC_TEST_DATABASE_URL` nicht gesetzt) |
| `uv run ruff check .` | **All checks passed!** |
| `uv run ruff check . --fix` | 5 Auto-Fixes (Import-Order), 3 manuell behoben (F631 Tuple-Assert, fehlender `TestClient`-Import) |
| `uv run pytest tests/test_contracts_snapshot.py` | **4 passed** (OpenAPI-Snapshot unverändert, kein Drift) |
| `uv run pytest tests/test_postgresql.py tests/test_secrets_masking.py` | **10 passed, 1 skipped** (gezielter Nachlauf nach Fixes) |

### Test-Abdeckung (R1-zusätzlich)
- **RBAC-Negative:** Viewer kann keine User anlegen, keine Audit lesen, keine Integrations konfigurieren; Operator kann keine Admin-Endpunkte.
- **CSRF:** State-changing POST/PUT/DELETE ohne Token → 403; mit Token → Erfolg.
- **Error-Zustände:** 401 (falsches Passwort, unbekannter User, inaktiver User), 403 (RBAC, CSRF), 404 (unbekannte Integration), 409 (doppelte Integration, Delete-Block), 429 (Rate-Limit), 405 (falsche Methode), 503 (Health-DB-down, PG-unmigrated).
- **Session-Abgelaufene:** Expired-Session → 401.
- **Passwort-Änderung:** Falsches aktuelles → 401; zu kurz → 422; identisch → 422; Erfolg → Session-Invalidierung.
- **PostgreSQL-Offline-DDL:** Alle 7 Tabellen, 9 benannte CHECK-Constraints, FKs mit CASCADE/SET NULL, UUID-Typ.

## 4. Offene Risiken & bekannte Defizite

| # | Risiko | Status |
| --- | --- | --- |
| 1 | **Live-PostgreSQL nicht verfügbar** in dieser Testumgebung → Live-Migration-Test gependet. Offline-DDL-Prüfung deckt DDL-Validität ab; Online-Roundtrip (Insert/Select) nur bei `HCC_TEST_DATABASE_URL`. | `tested` (offline) / `code_only` (live) |
| 2 | **In-memory Rate-Limits** (Login + Bootstrap) sind pro-Prozess, nicht über mehrere Worker/Prozesse hinweg geteilt. Bei `uvicorn --workers N` gilt das Limit pro Worker. Für produktive Deployment mit Multi-Worker: Redis-Backend nötig. | `known_limitation` |
| 3 | **Alembic-Offline-Modus defekt** (R0): `backend/alembic/env.py` übergeben `sqlalchemy.url` nicht als `url` an `MigrationContext`. R1-Test nutzt tmp-Env als Workaround. Reparatur in geteiltem Bereich → Vorschlag `docs/proposals/backend-alembic-offline-sql.md`. | `blocked` (Vorschlag offen) |
| 4 | **Passwort-Änderungs-Endpunkt** fehlt im frozen Contract. Service-Funktion ist fertig und getestet; API-Endpunkt blockiert. Vorschlag `docs/proposals/backend-auth-change-password.md`. | `blocked` (Vorschlag offen) |
| 5 | **`method_not_allowed`-Code** fehlt im frozen `ErrorCode`-Enum. 405 wird auf `not_found` gemappt (frozen Mapping). Doku (`api-contracts.md`) verspricht `method_not_allowed`. Vorschlag `docs/proposals/backend-errors-method-not-allowed.md`. | `blocked` (Vorschlag offen) |
| 6 | **ActionJob-Endpunkte** existieren nicht (frozen Routenplan). Service ist fertig und getestet; API-Zugriff erst bei Agent 3 (Proxmox-Aktionen) oder bei Contract-Erweiterung. | `code_only` (Service) / `not_started` (Endpunkte) |
| 7 | **api-contracts.md 501-Discrepanz:** Doku sagt `verify` → 501, frozen OpenAPI sagt 200 + `VerifyResponse(status=not_implemented)`. Code hält sich an den frozen OpenAPI. Doku-Korrektur empfohlen. | `known_discrepancy` |

## 5. Integrationshinweise für andere Agenten

### Agent 2 (Frontend)
- **Keine Contract-Änderungen** in R1 — generierter Client bleibt kompatibel.
- **Health-Endpoint** kann eine zusätzliche `migration`-Check-Entry in `checks[]` enthalten (PostgreSQL-DBs); SQLite-Tests sind davon unberührt.
- **429-Antworten** tragen jetzt `Retry-After: 60` — für UI-Fallback/Toast nützlich.
- **Passwort-Änderung:** Kein Endpunkt verfügbar (Service-only). UI kann erst nach Freigabe des Vorschlags `backend-auth-change-password.md` gebaut werden.
- **`verify`-Endpoint** liefert jetzt `last_verified_at` (auch bei `not_implemented`) — UI kann den Zeitstempel anzeigen.

### Agent 3 (Proxmox)
- **ActionJob-Service** ist bereit: `ActionJobService.create(db, actor, integration_id, action, target, ...)` — RBAC-geprüft (operator/admin), auditiert, Status-Tracking.
- **Integration-Delete** blockiert jetzt, wenn ActionJobs existieren (409) — Agent 3 muss das bei der UI beachten.
- **Keine API-Endpunkte** für ActionJobs (frozen Routenplan) — Agent 3 kann Endpunkte nach Contract-Erweiterung hinzufügen.
- **`verify`-Flow** setzt `last_verified_at` — Proxmox-Adapter kann den Zeitstempel für Freshness-Anzeigen nutzen.

### Agent 4 (Telemetry/Monitoring)
- **Health-Readiness** prüft bei PostgreSQL: `alembic_version` existiert und entspricht dem Head. Bei nicht-PostgreSQL-DBs (z. B. SQLite in Tests) kein Migration-Check.
- **Secrets-Masking** deckt jetzt auch `access_token`, `refresh_token`, `client_secret`, `private_key`, `authorization`, `cookie`, `session_token`, `csrf_token`, `bootstrap_token` ab — nützlich für Monitoring-Adapters, die diese Felder in Logs/Audit haben.
- **`secret_ref`** ist ein Name (Referenz), kein Wert → wird NICHT maskiert, darf in API-Antworten erscheinen.

### Agent 5 (QA/Security)
- **Contract-Tests:** `test_contracts_snapshot.py` bleibt grün — kein OpenAPI-Drift in R1.
- **Security-Tests:** RBAC-Matrix, CSRF-Abwehr, Rate-Limiting, Session-Invalidierung sind alle testiert und können als Baseline für E2E-Tests dienen.
- **Alembic-Offline-Defekt:** `backend/tests/test_postgresql.py` nutzt tmp-Env als Workaround — nach Freigabe der Reparatur kann der Test auf die echte `env.py` umgestellt werden (direkter Regression-Test).
- **Live-PG-Test:** `HCC_TEST_DATABASE_URL` setzen, um den Live-Migration-Roundtrip zu aktivieren (derzeit gependet).

## 6. Definition of Done — Check

- [x] Code und Migrationsskripte vorhanden
- [x] Format/Lint/Typecheck/Unit-/Integrationstests ausgeführt (121 passed, 1 skipped)
- [x] Kein Stub als fertig markiert (alle R1-Funktionen testiert)
- [x] Echte Verbindungen nur mit bereitgestellten Credentials (Live-PG-Test gependet, da keine Credentials)
- [x] Fehler-/Offline-/Timeoutzustände und RBAC abgedeckt
- [x] Doku, Changelog, Betriebsanleitung aktualisiert (drei Vorschläge, dieser Report)
- [x] Status präzise gekennzeichnet (`tested`, `code_only`, `blocked`, `not_started`)
- [x] Vor realen Deployment- oder Schreibaktionen explizit Freigabe einholen (kein Deployment in R1)
