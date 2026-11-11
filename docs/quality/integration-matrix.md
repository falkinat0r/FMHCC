# R1 — Integrations-/Test-Matrix (QA, Agent 5)

Stand: 2026-11-10 · Branch `feature/qa`

Verknüpft die verbindlichen Anforderungen (MASTER_PROMPT,
`docs/api-contracts.md`, `docs/DEPLOYMENT_PLAYBOOK.md`) mit den konkreten,
**ausgeführten** Tests. Status: ✅ bestanden (R1-Erstlauf), 🟡 nur statisch,
🔴 nicht abgedeckt (mit Begründung).

## 1. Unit/Contract (R0, `backend/tests/`) — 63 Tests

| Anforderung | Test | Status |
| --- | --- | --- |
| OpenAPI-Snapshot stabil | `test_contracts_snapshot.py` | ✅ |
| Dokumentierte Endpunkte existieren | `test_contracts_snapshot.py` | ✅ |
| Enum-Persistenz (`values_callable`) | Service-Tests | ✅ |
| Auth-Flows (bootstrap/login/logout/me) | `backend/tests/test_auth*` | ✅ |
| RBAC-Grundmatrix | `backend/tests/test_rbac*` | ✅ |
| Fehler-Handling (ApiError → Envelope) | `backend/tests/test_errors*` | ✅ |

Ausführung: `uv run pytest` in `backend/` → **63 passed** (Pipeline-Gate 3).

## 2. QA-Suite (R1, `tests/` auf Repository-Root) — 118 Tests

Ausführung: `uv run --project backend python -m pytest tests -q` →
**118 passed** (Pipeline-Gate 5). Fixtures in `tests/conftest.py`
(isolierte Cookie-Jars pro Rolle, Bootstrap-/Login-Helfer, Rate-Limiter-Reset).

### 2.1 Contract (`tests/contract/`) — 19 Tests

| Anforderung | Test | Status |
| --- | --- | --- |
| Error-Envelope `code/message/request_id` (+ optional `details`) | `test_openapi_contract.py` | ✅ |
| Alle Listen-Endpunkte → `Paged_*`-Envelope | `test_openapi_contract.py` | ✅ |
| `secret_ref` anyOf[string\|null] + Pattern/Länge | `test_openapi_contract.py` | ✅ |
| Passwortfelder `maxLength=200`, Mindestlängen | `test_openapi_contract.py` | ✅ |
| `integration_id` Pattern/Länge | `test_openapi_contract.py` | ✅ |
| Snapshot ↔ App: kein Drift | `scripts/qa/check_openapi_drift.py` (Gate 4) | ✅ |

### 2.2 RBAC (`tests/security/test_rbac_matrix.py`) — 36 Tests

| Anforderung | Status |
| --- | --- |
| Rollen admin/operator/viewer × Lese-Endpoint | ✅ |
| Rollen × Schreib-Endpoints (Users, Integrations, Audit) | ✅ |
| Unauthentifiziert → 401 (vor Validierung) | ✅ |
| Deaktivierter Nutzer → 401 (auch mit gültiger Session) | ✅ |

### 2.3 CSRF (`tests/security/test_csrf_matrix.py`) — 22 Tests

| Anforderung | Status |
| --- | --- |
| Double-Submit: Token = `hcc_csrf`-Cookie | ✅ |
| POST/PUT/PATCH ohne Token → 403 | ✅ |
| POST/PUT/PATCH mit falschem Token → 403 | ✅ |
| GET-Endpoints benötigen kein CSRF-Token | ✅ |
| Login/Bootstrap (Session-erschaffend) ohne Token erlaubt | ✅ |

### 2.4 Session-/Cookie-Sicherheit (`tests/security/test_session_security.py`) — 8 Tests

| Anforderung | Status |
| --- | --- |
| `hcc_session`: HttpOnly, Path=/, SameSite=lax | ✅ |
| `hcc_csrf`: **nicht** HttpOnly (Double-Submit) | ✅ |
| Secure-Flag bei `cookie_secure=true` (Produktion) | ✅ |
| Token persistiert als SHA-256-Hash | ✅ |
| TTL (absolut + Inaktivität) → 401 nach Ablauf | ✅ |
| Logout widerruft Session sofort | ✅ |
| Deaktivierter User: laufende Session → 401 | ✅ |

### 2.5 Auth-Härtung (`tests/security/test_auth_hardening.py`) — 5 Tests

| Anforderung | Status |
| --- | --- |
| Login-Rate-Limit → 429 mit Error-Envelope | ✅ |
| Falsches Passwort → 401 (kein User-Enum-Unterschied im Body) | ✅ |
| Bootstrap ohne gültiges Token → 401/403 | ✅ |
| Bootstrap doppelt → 403 (einmalig) | ✅ |

### 2.6 Secret-Leakage (`tests/security/test_secret_leakage.py`) — 7 Tests

| Anforderung | Status |
| --- | --- |
| 422-Details spiegeln keine Passwortwerte | ✅ |
| Audit-`details` maskiert | ✅ |
| `secret_ref` (Name) sichtbar, **Wert** nie in API-Response | ✅ |
| `viewer`-Rolle erhält `secret_ref=null` | ✅ |

### 2.7 Input-Validierung (`tests/security/test_input_validation.py`) — 21 Tests

| Anforderung | Status |
| --- | --- |
| Path-Traversal in Pfadsegmenten → 404/401, kein 500 | ✅ |
| Malformed UUID (authentifiziert) → 422-Envelope | ✅ |
| Injection-Versuche in `integration_id`/`username` → 422/404 | ✅ |
| Oversized Parameter (`page_size>200`, `name>128`) → 422 | ✅ |
| Nicht-JSON-Body → 422, kein Traceback | ✅ |

## 3. Frontend (R1-Erstausführung) — Gate 6 der Pipeline

| Schritt | Tool | Status |
| --- | --- | --- |
| Typecheck | `npx tsc -b --noEmit` | ✅ |
| Build | `npm run build` (vite) | ✅ |
| Unit-Tests (API-Client) | `npx vitest run` (7/7) | ✅ |
| Lint | `npm run lint` (eslint 9) | ✅ |

## 4. Statische / infrastrukturelle Gates

| Gate | Tool | Status |
| --- | --- | --- |
| Secret-Scan | `scripts/qa/scan_secrets.py` | ✅ (0 Befunde) |
| Backend-Lint | `ruff check` | ✅ |
| OpenAPI-Drift | `scripts/qa/check_openapi_drift.py` | ✅ (schreibfrei) |
| Deploy-Invarianten | `scripts/qa/check_deploy_artifacts.py` | ✅ |
| Dependency-Audits | `uv audit`, `npm audit --omit=dev` | ✅ (Network: BLOCKED-semantik) |

## 5. E2E im Ziel-LXC (🟡 vorbereitet, nicht in R1 ausgeführt)

`tests/e2e/e2e-smoke.sh` (8 Schritte über nginx-Loopback): Health,
Version, OpenAPI, Login (HttpOnly), RBAC, CSRF, Error-Envelope, SPA.
**Ausführung erst nach Merge im LXC** — R1 darf keine produktive
Infrastruktur ändern (Projektregel 5/8). Reibungspunkte (z. B. fehlende
`curl`/`jq`) meldet das Skript selbst.

## 6. Nicht abgedeckt (bewusst)

| Bereich | Begründung |
| --- | --- |
| Adapter-Integration (Proxmox, etc.) | KI/Agent-Funktionalität out of Scope (Regel 6); Adapter-Verify bleibt R0-Verhalten |
| Reales LXC-Deployment | keine produktiven Änderungen ohne Freigabe (Regel 5) |
| Last-/Penetrationstests | nicht im R1-Scope; Rate-Limit-/Cookie-Verhalten ist als Findung S3/S4 dokumentiert |
