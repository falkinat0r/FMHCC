# R0 Foundation — Übergabebericht (Handoff)

**Datum:** 2026-11-10
**Branch:** `foundation` (Worktree `C:\Users\muehleisen\Documents\hcc-foundation`)
**Foundation-Commit:** `c9c9553` (parent: `e7de34a` Initial HCC project specifications)
**Basis-Dokumente:** `AGENTS.md`, `MASTER_PROMPT.md`, `docs/DEPLOYMENT_PLAYBOOK.md`,
`docs/PARALLEL_WORKFLOW.md` (vollständig gelesen und befolgt)

## 1. Ausgangslage (Vortag)

Die gestrige Session (beschädigt/unterbrochen) hatte einen vollständigen
Backend-Entwurf, Config und Tests **uncommittet** im Worktree hinterlassen.
Repo und Git-Objekte waren intakt (nur ein harmloses dangling tree
`4b825dc…` in `git fsck`). Die Arbeit wurde übernommen, verifiziert,
repariert und ergänzt — keine Datei der gestrigen Arbeit wurde verworfen
(ein Debug-Rest `backend/_smoke.py` wurde entfernt).

## 2. Implementierungen (R0)

### 2.1 Backend (FastAPI, Python 3.14, venv via uv)
- `/api/v1`-API: health (live/ready), version, auth (bootstrap/login/logout/me),
  users, integrations (+verify), resources, audit — 15 Pfade.
- **Auth:** Bootstrap (einmalig, `HCC_BOOTSTRAP_TOKEN`, konstanter Zeitabgleich,
  `must_change_password`), Login (Rate-Limit), Server-Sessions
  (Hex-Token, nur SHA-256 persistiert, 12 h TTL, Revocation),
  CSRF Double-Submit (Cookie `hcc_csrf` ↔ Header `X-CSRF-Token`,
  Exemption nur login/bootstrap), Argon2id.
- **RBAC:** `viewer < operator < admin`, zentrale Berechtigungs-Keys,
  serverseitig pro Endpunkt.
- **Audit:** append-only, `user_id` FK `ON DELETE SET NULL`, Details-Maskierung.
- **Error-Envelope:** `{error:{code,message,details,request_id}}` über alle
  4xx/5xx; `UnhandledErrorMiddleware` (ASGI) macht 500-Envelope
  deterministisch (Starlette 1.10 re-raist sonst ServerErrors); Request-Id
  via Contextvar/Middleware.
- **Middleware-Ordung:** RequestID → Session → CSRF → UnhandledError → Router.
- **Contracts (frozen):** `backend/app/contracts/` + Snapshot
  `backend/contracts/openapi.v1.json` (generiert, `scripts/generate-openapi.py`,
  Drift-Test `test_contracts_snapshot.py`; Error-Envelope + `Paged_*`-Schemas
  im `components.schemas` dokumentiert).
- **Adapter-Interface (frozen):** `IntegrationAdapter`-Protokoll,
  `BaseAdapter`, `AdapterState`-Fehlerhierarchie, `ResourceRecord`,
  `EnvSecretsProvider` (nur `secret_ref`, keine Werte in DB/Logs/API),
  Registry `app/integrations/registry.py` — **R0 bewusst leer**; Verify
  antwortet ehrlich `501 not_implemented` (kein Stub).
- **Inventar:** `upsert_resources` (Dedup über
  `(integration_id, resource_type, external_id)`, Relations mit Evidenz).
- **DB:** Alembic-Initialmigration `0001_initial` (upgrade/downgrade geprüft);
  Enum-Spalten als `Enum(native_enum=False, create_constraint=True,
  values_callable=…)` — persistieren `.value`, CHECK-Namen **identisch** zur
  Migration (NAMING_CONVENTION in `app/db/base.py`); alle Zeitstempel UTC.

### 2.2 Tests (63, alle grün)
Auth (bootstrap/login/logout/csrf/rbac), Contracts-Snapshot, Error-Envelope,
Health, Version, Models (inkl. Session-Cascade, Audit-Maskierung,
Upsert/Relations), Adapter-Interface (FakeAdapter gegen Protokoll),
Migration (upgrade/downgrade/Revisions-Status), Pagination.

### 2.3 Deployment-Gerüst (nicht in echter Infrastruktur ausgeführt)
- `scripts/deploy-lxc.sh` — idempotent: Pakete, uv (ohne curl|sh, via
  Python-Venv), User `hcc`, PostgreSQL-Rolle/DB (kein Superuser, Passwort
  nur in `/etc/hcc/.pg_password` 0600), Release nach
  `/opt/hcc/releases/<sha>`, `/opt/hcc/current`-Symlink,
  `/etc/hcc/hcc.env` (0640, Bootstrap-Token generiert), systemd-Unit, nginx-Site.
- `deploy/systemd/hcc-api.service` — `User/Group=hcc`,
  `WorkingDirectory=/opt/hcc/current/backend`, `EnvironmentFile=/etc/hcc/hcc.env`
  (+ optional `secrets.env`), `ExecStartPre=alembic upgrade head`,
  Bind `127.0.0.1:8000`, `Restart=on-failure`, Hardening
  (`NoNewPrivileges`, `ProtectSystem=full`, `PrivateTmp`, …).
- `deploy/nginx/hcc.conf` — statisches `frontend/dist`, `/api/` → Loopback,
  Sicherheits-Header, SSE-ready (`proxy_buffering off`); TLS via Tailscale
  Serve empfohlen (HTTP nur isoliertes Testnetz).

### 2.4 Frontend (R0-Shell)
`index.html`, `src/main.tsx`, `src/App.tsx` (Session-Prüfung + Routen
`/login`, `/`), `src/pages/Login.tsx`, `src/pages/Dashboard.tsx`
(Integrations-/Ressourcen-Listen aus echten v1-Endpoints; leer = ehrlich
"keine konfiguriert"), `src/api/client.ts` (CSRF Double-Submit,
Error-Envelope-Parsing, `credentials: include`), `src/styles/global.css`,
`vitest.setup.ts`, `eslint.config.js`, Unit-Test `src/api/client.test.ts`
(CSRF-Header, Envelope-Parsing), `src/api/generated/README.md`
(openapi-typescript-Workflow).

**Status: `code_only`** — Build/Typecheck/Vitest auf der
Entwicklungsmaschine **nicht ausführbar** (Node.js nicht installiert).
Siehe Risiken §5.

### 2.5 Doku
- `docs/architecture.md` — Systemübersicht, Stack, **verbindliche
  Verzeichnis-Konventionen** (Umsetzung der PARALLEL_WORKFLOW-Tabelle),
  Schichten/Middleware, Datenmodell, Adapter-Konzept, Deployment,
  R0-Known-Limitations.
- `docs/api-contracts.md` — Grundregeln, Error-/Paging-Envelope,
  RBAC-Endpunkt-Tabelle (alle 15 Pfade), Schemata, Änderungsprozess,
  Client-Generierung.
- `README.md` — Status-Sektion R0 ergänzt.

## 3. Getestete Schritte (konkret ausgeführt)

| Befehl (Ort) | Ergebnis |
| --- | --- |
| `uv run pytest` (in `backend/`) | **63 passed** (≈30 s, in-memory SQLite) |
| `uv run ruff check .` (in `backend/`) | **All checks passed** |
| `uv run --project backend python scripts/generate-openapi.py` | Snapshot geschrieben, 15 Pfade; Snapshot-Test grün |
| `git branch --show-current` / `git status` | `foundation`, Working Tree clean nach Commit |
| `git fsck --full` (beide Repos) | intakt (1 dangling tree, harmlos) |
| Empirische SQLAlchemy-Verifikation | Enum-Read/Write, CHECK-NNamen, UUID-Binds (Scripts in Temp, nicht committet) |
| `bash -n scripts/deploy-lxc.sh` | **nicht ausführbar** auf dieser Windows-Maschine (Git-Bash blockiert, "Zugriff verweigert", WSL nicht vorhanden) — manuell gegengeprüft, **im LXC vorerst ausführen** |

## 4. Wichtige Entscheidungen

1. **Contracts nicht angefasst:** Alle Fixes erfolgten in Code/Tests, nie in
   Pydantic-Contracts oder OpenAPI-Shape (Frozen, R0). Der
   OpenAPI-Snapshot wurde nur regeneriert (keine Schema-Änderung).
2. **Enum-Design:** `values_callable` persistiert `.value` (StrEnum),
   CHECKs aus dem Typ (Namen über Naming-Convention) — Modell-Metadata und
   Migration sind DDL-identisch, kein Autogenerate-Drift.
3. **Logout braucht CSRF** (state-aendernd, Session vorhanden): Test korrigiert
   (Double-Submit-Header ergänzt), nicht die Middleware-Semantik.
4. **Kein Node.js → Frontend ehrlich als `code_only`** deklariert statt
   "bestanden" zu behaupten.

## 5. Offene Risiken / Grenzen

- **Frontend nicht verifiziert:** `tsc -b`, `vite build`, `vitest run`,
  `eslint` auf keiner Maschine mit Node >= 20.19 laufen. **Muss im
  Integrationsreview bzw. in Agent 2 nachgeholt werden**
  (`cd frontend && npm install && npm run build && npm run typecheck &&
  npm test && npm run lint`).
- **deploy-lxc.sh** nur statisch geprüft (Kein Bash auf Dev-Maschine);
  Syntax-/Lauftest im LXC vor erster Nutzung: `bash -n scripts/deploy-lxc.sh`.
- **Keine echte Infrastruktur angefasst:** kein Proxmox/LXC-Deployment,
  keine PostgreSQL-Instanz, kein Network-Zugriff — wie beauftragt.
- **Adapter-Registry leer** (Design-Entscheid R0): `PUT integrations`
  funktioniert, `POST …/verify` → `501 not_implemented`.
- **Test-Daten sind klar markierte Placeholders** (z. B.
  `test-bootstrap-token-0123456789abcdef`) — keine echten Secrets;
  Produktions-Bootstrap-Token wird erst vom Deployment-Skript generiert.
- **PostgreSQL-Laufpfad nur indirekt geprüft** (SQLite in Tests +
  PostgreSQL-DDL-Kompilation); Live-Migration gegen PostgreSQL im LXC
  (`ExecStartPre`) bleibt Teil der Abnahme.
- Git zeigt LF→CRLF-Warnings beim Commit (Windows-Checkout, `core.autocrlf`
  nicht gesetzt) — funktional irrelevant, bei Bedarf Repo-weit
  normalisieren.

## 6. Integrationshinweise (Betreiber / nächste Sessions)

1. **Review:** `git diff e7de34a..c9c9553` (Worktree
   `hcc-foundation`), Fokus: Contracts (`backend/app/contracts/`,
   `backend/contracts/openapi.v1.json`), Migration
   (`backend/alembic/versions/0001_initial.py`), CSRF/RBAC
   (`backend/app/auth/`), Deployment-Dateien.
2. **Merge in `main`** durch Betreiber nach Review (kein Auto-Merge,
   AGENTS.md Regel 3/4). Voraussetzungen für parallele Sessions sind dann
   erfüllt (PARALLEL_WORKFLOW §Voraussetzungen 1–2).
3. **Parallele Agenten** starten mit den Besitzbereichen aus
   `docs/PARALLEL_WORKFLOW.md` / `docs/architecture.md` §3 — die
   Verzeichnisstruktur ist final; Agent 2 (Frontend) baut auf der Shell
   auf und ersetzt die R0-Shell-Typen in `src/api/client.ts` durch
   `src/api/generated/schema.ts` (Workflow: `frontend/src/api/generated/README.md`).
4. **Contract-Änderungen** ausschließlich über
   `docs/proposals/<agent>-<topic>.md` + Snapshot-Regenerierung.
5. **Deployment** erst nach Freigabe: `sudo scripts/deploy-lxc.sh <checkout>
   --start` im LXC; danach einmalf Admin per `POST /api/v1/auth/bootstrap`
   (Token in `/etc/hcc/hcc.env`).
