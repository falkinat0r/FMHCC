# HCC 2.0 — Architektur (R0 Foundation)

**Status:** R0. Dieses Dokument ist die endgültige Quelle für
Verzeichnis-Konventionen (siehe auch `docs/PARALLEL_WORKFLOW.md`).
Abweichungen der Agenten von dieser Struktur sind zu korrigieren, nicht
umgekehrt.

## 1. Systemübersicht

```
                 ┌────────────────────────────────────────────┐
   LAN /         │            Debian-LXC (unpriv.)            │
   Tailscale ───▶│  nginx (:8080, TLS via Tailscale Serve)   │
                 │   ├─ static: /opt/hcc/current/frontend/dist│
                 │   └─ /api/ ─▶ 127.0.0.1:8000 (FastAPI)     │
                 │  hcc-api.service (User=hcc, systemd)       │
                 │   ├─ Alembic-Migration (ExecStartPre)      │
                 │   └─ Adapter-Layer ──▶ Proxmox/TrueNAS/…   │
                 │  PostgreSQL (User hcc, nur lokal)          │
                 └────────────────────────────────────────────┘
```

- **Kein Docker im LXC**, native systemd-Dienste.
- Das Backend lauscht **nur auf Loopback**; nginx ist einziger
  Netzwerk-Einstiegspunkt.
- Externe Integrationen (Proxmox, TrueNAS, Pi-hole, Tailscale, Docker,
  Monitoring) sind **abschaltbare Adapter**; eine nicht erreichbare
  Integration darf HCC nie blockieren.

## 2. Stack

| Schicht    | Technologie                              | Begründung                            |
| ---------- | ---------------------------------------- | ------------------------------------- |
| Backend    | Python ≥ 3.12, FastAPI, SQLAlchemy 2, Alembic | versionierte API, ORM, saubere Migrationen |
| DB         | PostgreSQL (Produktion), SQLite (Tests)  | relationale Konsistenz, Tests isoliert |
| Auth       | Argon2id, Server-Sessions, Double-Submit-CSRF | keine JWT-Clientside-Persistenz |
| Frontend   | React 19 + TypeScript + Vite + Vitest    | SPA gegen versionierte API            |
| Typen      | OpenAPI-Snapshot als verbindlicher Contract | Frontend generiert Client-Typen     |
| Deployment | Debian-LXC, systemd, nginx               | Playbook `docs/DEPLOYMENT_PLAYBOOK.md` |

## 3. Repository-Struktur (verbindlich)

```
backend/
  app/
    api/
      deps.py              Session-Context-Middleware
      v1/                  Endpoints unter /api/v1 (frozen Routenplan, R0)
    audit/                 Audit-Service (append-only, Maskierung)
    auth/                  bootstrap, sessions, csrf, rbac, rate_limit, hashing
    adapters/              Adapter-Protokoll, Fehlerhierarchie, SecretsProvider (frozen)
    contracts/             EINGEFRORENE Pydantic-Contracts (frozen, R0)
    db/                    Engine, Session-Factory, Base + NAMING_CONVENTION
    integrations/          Adapter-Registry (R0: bewusst leer)
    integrations/<kind>/   Agent 3+4: konkrete Adapter (proxmox, monitoring, …)
    inventory/             Dedup/Normalisierung (upsert_resources, frozen)
    inventory/<kind>/      Agent 3+4: Integrationsspezifische Normalisierung
    models/                ORM-Modelle (Schema R0-frozen)
    users/                 User-/Rollen-Service
    config.py              pydantic-settings (HCC_* Prefix)
    errors.py              Error-Envelope, Exception-Handler, UnhandledErrorMiddleware
    logging_setup.py       strukturiertes Logging, Request-Id-Context
    main.py                App-Factory (Middleware-Ordung, OpenAPI-Injektion)
  alembic/                 Migrationen (0001_initial R0-frozen)
  contracts/openapi.v1.json  Verbindlicher Contract-Snapshot
  tests/
    auth/                  Agent 1: Auth-Tests
    integrations/          Agent 4: Adapter-Tests
    proxmox/               Agent 3: Proxmox-Tests
  scripts/                 (keine) — Repo-Scripts liegen in scripts/ (root)
contracts → siehe backend/contracts
deploy/
  systemd/hcc-api.service  systemd-Unit (Playbook §6)
  nginx/hcc.conf           nginx-Site (SPA + /api/-Proxy)
docs/
  architecture.md          (dieses Dokument)
  api-contracts.md         Contract-Regeln + Endpunkt-Verzeichnis
  foundation-handoff.md    Übergabebericht R0
  proposals/               Contract-Änderungsvorschläge (AGENTS.md Regel 4)
  quality/                 Agent 5 (QA)
frontend/
  src/
    api/
      client.ts            Fetch-Wrapper (CSRF Double-Submit, Error-Envelope)
      generated/           generierte Typen (Agent 2 KEIN Schreibzugriff)
    components/            Agent 2
    features/              Agent 2
    pages/                 Agent 2
    styles/                Agent 2
  index.html, vite.config.ts, tsconfig*.json, package.json
scripts/
  deploy-lxc.sh            idempotentes LXC-Deployment
  generate-openapi.py      Contract-Regenerierung
  qa/                      Agent 5 (QA)
tests/                     (root) Agent 5: e2e/, security/
```

**Besitzbereiche** exakt wie in `docs/PARALLEL_WORKFLOW.md` — dieses
Verzeichnislayout ist die Umsetzung dieser Tabelle. `backend/app/contracts/**`
und `backend/alembic/**` sind gemeinsames Eigentum und nur über
`docs/proposals/<agent>-<topic>.md` änderbar.

## 4. Backend-Architektur

### 4.1 Schichten

```
API (app/api/v1)  →  Contracts (app/contracts, frozen)  →  Services
     │                        │                              │
     │                        │                              ▼
     └──── RBAC (app/auth/rbac) ────  Models (app/models) + DB
                                   Audit (app/audit)
```

- Endpoints validieren via Pydantic-Contracts, prüfen RBAC
  (`require_permission`), schreiben Audit-Events und mappen Fehler in die
  Error-Envelope.
- Inventar-Schreibweg ist **einzig** `app/inventory/base.upsert_resources`
  (aufgerufen von Adapter-Discover); die API ist R0 read-only für Ressourcen.

### 4.2 Middleware-Ordung (außen → innen)

```
RequestID → SessionContext → CSRF → UnhandledError → Route-Handler → Router
```

- `RequestID`: legt `request_id` (scope-gemeinsam) + Contextvar an.
- `SessionContext`: löst `hcc_session`-Cookie, setzt
  `request.state.current_user` (einmalig pro Request).
- `CSRF` (Double-Submit): nur state-aendernde Requests unter `/api/v1/`;
  Exemption: `/auth/login`, `/auth/bootstrap`; Fehlschlag → 403-Envelope.
- `UnhandledError`: fängt unbehaltene Exceptions → 500-Envelope (deterministisches
  Verhalten in TestClient, uvicorn und jedem ASGI-Server; Stacktraces nur
  serverseitig in Logs).

### 4.3 Auth & Sicherheit

- **Bootstrap:** einmalig, nur wenn keine User existieren, nur mit
  `HCC_BOOTSTRAP_TOKEN` (konstanter Zeitabgleich), Admin +
  `must_change_password=true`.
- **Sessions:** 32 Zufallsbytes als Hex, nur SHA-256-Hash persistiert,
  TTL standard 12 h, Revocation beim Logout.
- **Passwörter:** Argon2id.
- **RBAC:** `viewer < operator < admin`; Berechtigungen zentral in
  `app/auth/rbac.py`; Prüfung immer serverseitig pro Endpunkt.
- **Rate-Limit:** Sliding-Window pro Endpunkt (Login hart begrenzt).
- **Secrets:** DB speichert nur `secret_ref`; Werte über
  `EnvSecretsProvider` aus `/etc/hcc/secrets.env` (0640).
- **Audit:** append-only, `user_id` FK mit `ON DELETE SET NULL`
  (Events überleben User-Loeschung), Details-Field-Maskierung.

### 4.4 Datenmodell (R0-frozen)

| Tabelle            | Zweck                                              |
| ------------------ | -------------------------------------------------- |
| `users`            | Accounts, Rolle (`viewer/operator/admin`)          |
| `user_sessions`    | Session-Hash + Expires (UTC)                       |
| `integrations`     | Anbindungen; `secret_ref` statt Secret-Wert        |
| `resources`        | normalisiertes Inventar, Unique-Key `(integration_id, resource_type, external_id)` |
| `resource_relations` | Beziehungen, Unique `(source, target, relation_type)`, Evidenz |
| `action_jobs`      | idempotente Schreibanfänge (R1+), Schema frozen    |
| `audit_events`     | Audit-Log (append-only)                            |

- Enum-Spalten: `Enum(..., native_enum=False, create_constraint=True)` mit
  `values_callable` (persistiert `.value`), CHECK-Namen identisch zur
  Initialmigration (NAMING_CONVENTION in `app/db/base.py`).
- Alle Zeitstempel UTC. Zustände: `healthy / degraded / down / unknown /
  not_configured` — fachlich getrennt, keine Zufallswerte.

### 4.5 Adapter-Konzept (frozen Protokoll)

`app/adapters/base.py` definiert:

- `IntegrationAdapter` (Protokoll): `verify(config, secrets) -> AdapterStatus`,
  `discover(config, secrets) -> AsyncIterator[ResourceRecord]`, optional
  `act(...)` (in R0 nicht genutzt).
- `BaseAdapter`: abstrakte Basisklasse mit `kind` und Timeouts.
- `ResourceRecord`: normalisierte Entität für das Inventar
  (Typ, external_id, Status, Parent-Referenz für Relations).
- `AdapterError`-Hierarchie (`app/adapters/errors.py`) mit stabilem
  `AdapterState` (`ok / not_configured / auth_failed / unreachable / …`) —
  maschinell in API-Antworten überführbar.
- `app/integrations/registry.py`: Registry + `@register`. **R0: leer** —
  Verify-Endpunkt antwortet ehrlich mit `not_implemented` (501), kein Stub.
- Folge-Agenten liefern Adapter unter `app/integrations/<kind>/` und
  registrieren sie per Decorator; sie berühren Contracts/Migrationen nicht.

## 5. Frontend-Architektur

- **SPA** (React + TypeScript), gebaut nach `frontend/dist` (nginx).
- `src/api/client.ts`: einziger Zugriffspunkt auf die API;
  `credentials: "include"` (Cookies) + Double-Submit-Header
  `X-CSRF-Token` aus `hcc_csrf`-Cookie für state-aendernde Requests;
  Error-Envelope wird zentral geparst.
- `src/api/generated/`: Typen aus `backend/contracts/openapi.v1.json`
  (via `openapi-typescript`) — von Agent 2 nur lesbar.
- Entwicklung: Vite-Proxy `/api` → `127.0.0.1:8000` (siehe `vite.config.ts`).
- R0-Shell: Login + Dashboard-Layout mit echten v1-Endpoints
  (Integrations-/Ressourcen-Listen, leer = ehrlich `not_configured`).

## 6. Deployment

- LXC: unprivilegiert, Debian 13, 2 vCPU / 3 GiB (Planungswert).
  Details: `docs/DEPLOYMENT_PLAYBOOK.md`.
- `scripts/deploy-lxc.sh`: idempotentes Deployment (Pakete, uv, User,
  PostgreSQL-Rolle/DB, Release unter `/opt/hcc/releases/<sha>`,
  `/opt/hcc/current`-Symlink, `/etc/hcc/hcc.env` 0640, systemd, nginx).
- `hcc-api.service`: `User=hcc`, `EnvironmentFile=/etc/hcc/hcc.env`,
  `ExecStartPre=alembic upgrade head`, Bind `127.0.0.1:8000`,
  `Restart=on-failure`, Hardening (`NoNewPrivileges`, `ProtectSystem=full`, …).
- nginx: statisches SPA + `/api/` → Loopback-Backend; TLS bevorzugt via
  Tailscale Serve (HTTP nur im isolierten Testnetz).
- PostgreSQL: dedizierter User `hcc` (kein Superuser), nur lokal erreichbar.

## 7. Versionierung und Contracts

- Endpoints: `/api/v1/...` (Routenplan R0-frozen, see `backend/app/api/v1/`).
- Verbindlicher Contract: `backend/contracts/openapi.v1.json` (Snapshot-Test
  `backend/tests/test_contracts_snapshot.py` verhindert Drift).
- Contract-Änderung nur über `docs/proposals/<agent>-<topic>.md`
  (AGENTS.md Regel 4) + Snapshot-Regenerierung + Eintrag in
  `docs/api-contracts.md`.

## 8. R0-Known-Limitations

- Adapter-Registry leer: `POST/PUT integrations` möglich, Verify → 501
  `not_implemented` (bewusst, kein Stub).
- Frontend-Shell: kein Feature-Code (das ist Agent 2), kein E2E (Agent 5).
- Kein WebSocket/SSE in R0 (nginx ist vorbereitet, siehe `deploy/nginx/hcc.conf`).
- Monitoring-/Inventar-Funktionen folgen in R1+ gegen die frozen Contracts.
