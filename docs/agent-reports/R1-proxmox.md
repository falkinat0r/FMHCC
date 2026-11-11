# R1 Proxmox — Agent-Report (Agent 3)

Branch: `feature/proxmox` · Worktree: `C:\Users\muehleisen\Documents\hcc-proxmox`
Code-Commit: `339a701` (feat(proxmox): R1 Proxmox-Adapter, Inventar-Sync und Compute-Aktionen)
Kein Merge nach `main`; nur eigene Dateien (File-Ownership gemäß PARALLEL_WORKFLOW.md).

## 1. Umsetzter Funktionsumfang (Scope: `agent-tasks/03-proxmox.md`)

### API-Client (`backend/app/integrations/proxmox/client.py`)
- Nur API-Token-Authentifizierung: `Authorization: PVEAPIToken=<user>@<realm>!<token-id>=<secret>`;
  keine Passwort-/Ticket-Auth, keine Shell-Ausführung, keine Root-Passwoerter.
- TLS: Verifizierung ist Standard (`verify=True`); CA-Bundle konfigurierbar
  (`tls_ca_bundle`); Abschaltung nur explizites, WARNING-ge-loggtes Opt-in
  (`tls_verify_disabled`) — niemals Default.
- Timeouts über `AdapterConfig.timeout_seconds` (httpx-Timeout).
- Retry **nur** für idempotente GETs (Transportfehler/5xx) mit exponentiellem
  Backoff; POST-Aktionen werden nie wiederholt.
- Rate-Limiting: pro-Client-Mindestabstand (`rate_limit_per_second`, Default 5 req/s).
- Fehlermauerung auf die frozen `AdapterError`-Hierarchie:
  `AdapterAuthError` (401/403), `AdapterApiError` (sonstiges 4xx/5xx, Nicht-JSON,
  fehlendes `data`), `AdapterUnreachableError` (Connect/TLS, `details.tls`),
  `AdapterTimeoutError`. Fehlertexte ohne Secret-/URL-Teile (getestet).
- `get_optional` (403/404 → `None`), `get_tolerant` (jeder AdapterError → `None`),
  Healthcheck `GET /version` (ohne Auth-Zwang).
- Test-Transport: `set_test_transport()` (nur Tests; in Produktion `None`).

### Konfiguration (`config.py`)
- Secret-Wert (Env-Variable) im PVE-Format `<user>@<realm>!<token-id>=<secret>`
  (Fallback-Separator `:`); fehlend/ungültig → `AdapterConfigError`
  (state `not_configured`), 401/403 → `AdapterAuthError` (`auth_failed`).
- Optionen via `AdapterConfig.extra` (Strings): `rate_limit_per_second`,
  `max_retries`, `retry_backoff_seconds`, `tls_ca_bundle`,
  `tls_verify_disabled`, `fetch_resource_details`; ungültige Werte → sichere
  Defaults. `api_root` normalisiert auf `…/api2/json`.
- Versionsgate: `MINIMUM_PVE_MAJOR = 8` (PVE 7 ist EOL).

### Discovery (`discovery.py`, `normalize.py`)
- `verify()`: `GET /version` (TLS/Erreichbarkeit + Versionsgate) → `GET /nodes`
  (Token-Validität). Nur lesend.
- `capabilities()`: PVE-Version, Cluster-/Standalone-Modus (`/cluster`),
  Quorum-Kennwert (`/cluster/health`), Feature-Liste.
- `discover()`: Nodes **zuerst** (Parents für `upsert_resources`), dann VMs,
  dann LXC pro Node. Zweistufige Fehlerstrategie:
  - fundamental (`/nodes`): bricht mit AdapterError ab;
  - optionale Details (Node-Status/Storage/Tasks, VM-/LXC-Config, Snapshots,
    Cluster-Health): degradieren pro Ressource auf `None` — Rechte-Fehler
    oder Teilfehler blockieren den Rest nicht;
  - Offline-Node (`status: offline`): **keine** Node-spezifischen Requests,
    Resource ehrlich `down`.
- Normalisierung: rein, nur echte API-Werte, fehlend → `None` (nie erfunden);
  PVE-Größen (`32G`, MB-Config) → Bytes; Disks (scsi/ide/sata), Netzwerk
  (net0…), Snapshots, Storage, Tasks, Cluster/Quorum im Payload.
- Resource-Key: `external_id` = Node-Name / `str(vmid)` / `str(cid)`
  (cluster-eindeutig); Parent-Relation `runs_on` auf NODE.

### Status-Mapping (dokumentierter Entschluss)
| Quelle | Wert | HCC-Status |
|---|---|---|
| VM/LXC | running | healthy |
| VM/LXC | paused | degraded |
| VM/LXC | stopped | down |
| Node | online (+ Quorum ok) | healthy |
| Node | online, `quorum_ok=false` | degraded (Note im Payload) |
| Node | maintenance | degraded |
| Node | offline | down |
| sonst/unbekannt | — | unknown |

### Compute-Aktionen (`actions.py`)
- Nur **sanft**: qemu `status/start`, `status/shutdown` (ACPI),
  `status/restart` (ACPI); lxc `start`, `stop` (ohne Force), `restart`.
  Erzwungene Stops/Destroy/Migration sind bewusst nicht implementiert
  (`action_endpoint` → `None`).
- Node-Auflösung: `/cluster/resources?type=…&vmid=…` (funktioniert Standalone
  wie Cluster), Fallback per-Node-Abfrage `/nodes/{n}/{qemu|lxc}/{id}`.
- Proxmox antwortet asynchron mit UPID; `state=ok` = "vom Host akzeptiert"
  (Task-Polling `/nodes/{n}/tasks/{upid}` getestete Evidenz).
- `execute_compute_action()`: serverseitig RBAC (frozen Key `actions.run`),
  Bestätigungspflicht (422), idempotentes ActionJob-Handling
  (`idempotency_key`, frozen Schema), Statuslauf pending→running→succeeded/failed;
  Adapter-Fehler werden im Job getragen (error_state), nicht geworfen;
  Audit-Events `actions.compute.<verb>[.accepted|.failed|.replay]`
  über `app.audit.log.record_audit`.

### Inventar-Sync (`backend/app/inventory/proxmox/sync.py`)
- `sync_proxmox_inventory(db, integration, records)` — dünne, **synchron**
  Wrapper-Schicht um den einzigen frozen Schreibweg
  `app.inventory.base.upsert_resources`; liefert `SyncResult`
  (total/created/updated/relations_created). Kein zweiter Schreibweg.

### Adapter (`adapter.py`)
- `ProxmoxAdapter` (frozen `IntegrationAdapter`-Protokoll via `BaseAdapter`):
  `verify`, `capabilities`, `discover`, `health` (leichte `/version`-Prüfung),
  `act` (Confirmed-Check, Action-Whitelist, VMID/CT-ID-Validierung).
  `collect()` bleibt R0-Default `not_implemented`.
- **Kein** Import-Registrierung: explizit `register_proxmox_adapter()`
  (idempotent, weicht fremden Proxmox-Adaptiern aus) — die eingefrorene
  R0-Registry-Testbasis (FakeAdapter, kind=proxmox) bleibt unangetastet.
  Produktions-Hook ist Core-Vorschlag (siehe §5).

## 2. Betroffene Dateien (alle neu, alle Agent-3-eigen)

```
backend/app/integrations/proxmox/__init__.py
backend/app/integrations/proxmox/actions.py
backend/app/integrations/proxmox/adapter.py
backend/app/integrations/proxmox/client.py
backend/app/integrations/proxmox/config.py
backend/app/integrations/proxmox/discovery.py
backend/app/integrations/proxmox/normalize.py
backend/app/inventory/proxmox/__init__.py
backend/app/inventory/proxmox/sync.py
backend/tests/proxmox/__init__.py
backend/tests/proxmox/conftest.py
backend/tests/proxmox/fixtures/__init__.py
backend/tests/proxmox/fixtures/server.py
backend/tests/proxmox/test_actions.py
backend/tests/proxmox/test_adapter.py
backend/tests/proxmox/test_client.py
backend/tests/proxmox/test_config.py
backend/tests/proxmox/test_discovery.py
backend/tests/proxmox/test_inventory.py
docs/proposals/agent3-proxmox-core-integration.md
docs/agent-reports/R1-proxmox.md
```

Keine Änderungen an frozen Contracts, Migrationen, Registry, main.py,
api/v1-Endpoints, Testkonfiguration oder Dependencies.

## 3. Getestete Schritte (Auszug: ausgeführte Befehle, Ergebnis)

```
cd backend
uv run --extra dev ruff check .        # → All checks passed!
uv run --extra dev pytest              # → 165 passed (davon 102 neu: tests/proxmox)
uv run --extra dev pytest tests/proxmox -v   # → 102 passed
```

Deckung der 11 geforderten Mock-Szenarien (alle über `FakeProxmoxServer`
per `httpx.MockTransport`, kein Netzwerkzugriff, nur Test-Placeholders):

| # | Szenario | Test-Modul |
|---|---|---|
| 1 | Standalone-Host | test_discovery, test_inventory, test_actions, test_adapter |
| 2 | Multi-Node-Cluster (pve1/pve2 online, pve3 offline) | test_discovery, test_actions, test_inventory |
| 3 | Offline-Node (keine Requests dorthin, Status down) | test_discovery, test_inventory |
| 4 | Unreachable-API (ConnectError → `unreachable`) | test_client, test_discovery, test_adapter (HTTP) |
| 5 | Ungültiges Token (401 → `auth_failed`) | test_client, test_discovery, test_adapter (HTTP) |
| 6 | Unzureichende Berechtigung (403, Details degradieren, `/nodes` bricht ab) | test_client, test_discovery |
| 7 | Abgelaufenes TLS-Zertifikat (SSLError → `unreachable`, `details.tls=true`) | test_client |
| 8 | Fehlende API-Antwort (Nicht-JSON, fehlendes `data`, Nicht-Liste) | test_client, test_discovery |
| 9 | Fehlgeschlagener VM-Start (500 → Job `failed`, `error_state=api_error`, Audit `.failed`) | test_actions |
| 10 | Async-Task-Antwort (UPID, pollbar unter `/nodes/{n}/tasks/{upid}`) | test_actions, test_client |
| 11 | Fehlendes Quorum (Online-Nodes `degraded` mit Note) | test_discovery |

Zusätzlich: Retry-Nur-GET/Kein-POST-Retry, Timeout→`timeout`, 503-Flak,
`get_optional`/`get_tolerant`-Semantik, Rate-Limiter-Mindestabstand,
Token-Parsing (Format, Fallback, Fehler), api_root-Normalisierung,
Status-/Disk-/Network-/Snapshot-Normalisierung, Inventar-Dedup/Idempotenz
(2. Lauf: created=0, updated=n, keine Duplikate), RBAC (viewer 403,
Bestätigung 422), Idempotency-Replay (keine zweite Proxmox-Schreibaktion),
Secret-Leak-Prüfung (Meldungen/Details/last_error), HTTP-Verify-Endpunkt
(ok/not_configured/auth_failed/unreachable/version_unsupported/
not_implemented/admin-only), Registry (idempotent, keine Kollision mit
fremdem Proxmox-Adapter), eingefrorene R0-Suite bleibt grün
(incl. `test_contracts_snapshot` und `test_adapter_interface`).

## 4. Empfohlene minimale API-Token-Rechte

PVE-Token gehören einem User; Berechtigungen werden auf den User
(grundsätzlich auf Datacenter-Ebene) erteilt, das Token erbt sie.
Empfohlenes Minimum für diese Implementierung:

| Scope | Berechtigung | Zweck |
|---|---|---|
| Datacenter | `VM.Audit` | VM-/LXC-Listing, Status, Config, Snapshots (Read-only) |
| Datacenter | `VM.PowerMgmt` | start/shutdown/restart (nur für Aktions-Betrieb) |
| Jeder Node | `Sys.Audit` | Node-Listing/Status/Storage/Tasks, Cluster-Endpunkte |

Ohne Aktions-Betrieb reicht `VM.Audit` + Node `Sys.Audit`.
**Hinweis:** Empirische Validierung am realen System ausstehend (siehe §6) —
v. a. die Exaktheit bei `/cluster*` (PVE prüft Cluster-Endpunkte teils
über alle Nodes) und ob `/nodes/{n}/qemu` mit Datacenter-`VM.Audit` ohne
Pool-Einordnung ausreicht.

## 5. Benötigte Core-Änderungen (kein R1-Blocker, Proposal vorhanden)

Siehe `docs/proposals/agent3-proxmox-core-integration.md`:
1. Produktions-Registrierung (`register_all_adapters()` in `create_app`)
   — ohne den Hook antwortet der frozen Verify-Endpunkt ehrlich
   `not_implemented`.
2. R2: `POST /integrations/{id}/sync` (neuer Permission-Key `inventory.sync`,
   Operator).
3. R2: `POST /integrations/{id}/actions` (Idempotency-Key, frozen
   `actions.run`, ActionJob-Antwort).
4. R2: Konfigurations-Persistierung für `extra`-Optionen
   (JSON-Spalte `options` auf `integrations` via Migration empfohlen).

## 6. Offene Risiken / Annahmen (am realen System zu verifizieren)

- `/nodes`-Listing enthält `status` inkl. `offline` für Cluster-Mitglieder
  (Annahme; sonst fällt der Offline-Skip weg, aber die Status-Meldung
  über Detail-/Status-Endpoints bleibt korrekt, weil offline-Node 404/
  Timeout auf Details degradiert).
- `/cluster` liefert auf Standalone `[]` (nicht 404); `/cluster/health`
  existiert nur im Cluster (404 auf Standalone ist bereits toleriert).
- `/cluster/resources` funktioniert auch auf Standalone (PVE-Doku ja).
- `/api2/version` ist unauthentifzierbar (Healthcheck-Prämisse).
- Backup-Status wird **nicht** als eigene Resource gefahren (R1-Scope:
  Disks tragen nur `backup=0/1` aus der Config); Backup-Jobs wären R2.
- `verify()` prüft nur Envelope-Status von `/nodes` (nicht List-Shape);
  eine kaputte `/nodes`-Liste bricht erst in `discover()` ab.
- TLS-/Rate-Limit-Optionen sind im HTTP-Verify-Pfad derzeit nicht setzbar
  (`extra` bleibt leer, frozen Endpoint) — siehe Proposal Item 4.
- `succeeded` bei Aktionen bedeutet Proxmox-Akzeptierung (UPID), nicht
  Abschluss; Task-Polling-Endpunkt ist R2.
- Reale Schreibaktionen wurden ausschließlich gegen Mock-APIs getestet;
  ein Live-Test (autorisierte Test-VM, mit Freigabe) ist offen.

## 7. Integrationshinweise für Folge-Arbeit

- Tests laufen mit `uv run --extra dev pytest` aus `backend/`
  (keine neuen Dependencies; `httpx.MockTransport` reicht, kein
  pytest-asyncio).
- Neue Tests: `tests/proxmox/fixtures/server.py` (Szenario-Bauer
  `standalone_scenario`/`cluster_scenario`) und
  `tests/proxmox/conftest.py` (Helfer `make_config`/`make_client`/
  `discover_records`/`client_request`/`run`) wiederverwenden.
- Registry pro Test: Autouse-Fixture `_registry` in
  `tests/proxmox/conftest.py` setzt den echten Adapter, R0-Tests
  registrieren ihren Fake eigenständig (keine Kollision).
- Für QA: Secret-Ref der Test-Integration ist `HCC_TEST_PROXMOX_TOKEN`
  (Wert ist Test-Placeholder, gesetzt in der autouse-Fixture
  `_proxmox_env`); kein echtes Secret im Repo.
