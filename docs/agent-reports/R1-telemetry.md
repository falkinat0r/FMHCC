# Agent 4 — Monitoring & Integrations (R1 Telemetry) — Übergabebericht

**Branch:** `feature/telemetry`  ·  **Worktree:** `hcc-telemetry`  ·  **Commit:** (siehe unten)

Scope laut `agent-tasks/04-monitoring-integrations.md`: read-only
Monitoring-/Integrations-Ebene über vorhandene Infrastruktur, eventbasiert
normalisiert, fixturbasiert getestet, keine KI-/AI-Funktionen, keine
REST-Contract-Änderung (frozen), keine Merge nach `main`.

---

## 1. Implementierte Adapter (alle read-only)

| Adapter | `app/integrations/` | API / Modus | Auth | Status |
|---|---|---|---|---|
| **Prometheus** | `monitoring/prometheus.py` | HTTP `/api/v1/*` (query, query_range, label-values, buildinfo) | optional Basic (`secret_ref`) | template-only, versioned |
| **Grafana** | `monitoring/grafana.py` | `/api/health`, `/api/datasources` | optional (Token) | source_status, datasources |
| **Loki** | `monitoring/loki.py` | `/loki/api/v1/ready`, `/labels` | optional | labels, no version |
| **Uptime Kuma** | `monitoring/uptime_kuma.py` | `/api/status`, `/api/login`, `/api/monitor` | session-Login (`user:pass`) | **fixture-only, live verifizieren** |
| **Monitoring-Engine** | `monitoring/engine.py` | `extra.backend`-Auswahl + Auto-Erkennung (prometheus → uptime_kuma → grafana → loki) | — | delegiert an Backends |
| **Pi-hole** | `pihole/adapter.py` | v5 `api.php` + v6 REST (`/api/info/login`, `/api/auth`, `/api/stats/summary`, `/api/dns/blocking`) | v5: `pwhash` · v6: `X-FTL-SID` (Session) | v5/v6 capability-gated |
| **Docker** | `docker/adapter.py` + `docker/security.py` | Engine API (`/version`, `/info`, `/containers/json`, `/containers/{id}/stats`) | Unix-Socket / mTLS-TCP | **keine plain-TCP-Remote** |
| **Tailscale** | `tailscale/adapter.py` | **zwei getrennte Modi**: `api` (Management, `api.tailscale.com/api/v2`) + `local` (Local API `/localapi/v0/status`) | api: Bearer-Key · local: Basic (`tailscale debug local-creds`) | Management vs. lokaler Daemon getrennt |
| **TrueNAS** | `truenas/adapter.py` | REST v2.0 (`/api/v2.0/*`: `system/info`, `pool`, `pool/dataset`, `disk`, `smart/test/results`) | pro-Request Basic (`user:pass`) oder Bearer-API-Key | REST-Gate: ab 26.0 version-unsupported |

Gemeinsam: `monitoring/httputil.py` (Shared-HTTP-Client), `monitoring/base.py`
(Protokoll `BaseMonitoringBackend`), `monitoring/events.py`
(Ereignisnormalisierung/Dedup). Registrierung über
`app/integrations/registry.py` (`@register`), App-Wiring in
`app/integrations/__init__.py` (guarded `importlib` — ein kaputter Adapter
crasht die App nicht, Registry bleibt `not_implemented`).

---

## 2. API-Versionen & Auth (quellenbasiert verifiziert)

### TrueNAS — REST v2.0
- **Quellen:** `truenas/middleware` `restful.py`, `main.py`, `plugins/*`
  für Tags `TS-24.04.0`, `TS-24.10.0`, `TS-25.04.0`, `TS-25.10.0`,
  `TN-13.3-RELEASE`; `TS-26.0.0-BETA.3` (REST **entfernt**).
- **Auth:** kein Login-Endpoint, keine Cookies. Pro Request
  `Authorization: Basic base64(user:pass)` (Secret `user:pass`) **oder**
  `Bearer <api_key>` (Secret ohne `:`). 2FA aktiv ⇒ Basic nicht verfügbar;
  ab 25.04 API-Keys brauchen Server-AAL ≥ AA_LEVEL1.
- **Antworten:** rohes JSON, **kein Envelope** (Vorstellung widerlegt).
  Fehler: 422 `{"message","errno"}`, 404 `{"message"}`, 401/403 Klartext.
- **Feld:** `/system/info` → `version` (Nicht `version_string`).
- **Version-Gate:** auth-freier Probe `GET /api/v2.0/openapi.json`
  (404/405 ⇒ `AdapterVersionError`, da REST ab 26.0 weg).
- **ZFS-Events:** nur WebSocket → R1 pollt Pool-Daten (`scan.state/percentage`),
  kein Event-Abonnement.

### Tailscale — Management-API vs. lokale Client-Info (getrennt)
- **Local API:** `GET /localapi/v0/status` → `ipnstate.Status`
  (`BackendState`, `Self`, `Peers` dict). Zugang über Unix-Socket
  (`/var/run/tailscale/tailscaled.sock`, Host-Header `local-tailscaled.sock`)
  oder Loopback-HTTP (Port **41112**, alt 4112 deprecated). Optional Basic-Auth
  (`tailscale debug local-creds`). **Keine stabile öffentliche API** → Adapter
  behandelt Feldänderungen tolerant.
- **Management-API:** `GET api.tailscale.com/api/v2/tailnet/{tailnet}/devices`,
  Bearer-Key; Device-Felder `id`, `name[]`, `hostname`, `addresses`, `online`,
  `lastSeen`.
- **Moduswahl:** `extra.tailscale_mode` = `api` | `local`
  (Heuristik: `extra.tailnet` gesetzt ⇒ `api`).

### Pi-hole — v5/v6
- **v6 REST:** `/api/info/login` (Erkennung), `POST /api/auth` (Login →
  `session.sid`), danach Header `X-FTL-SID`; `/api/stats/summary`,
  `/api/dns/blocking`.
- **v5:** `/admin/api.php` mit `pwhash` (SHA-256-Hash des Passworts, kein
  Klartext-Login); `?versions` (Erkennung), `?summaryRaw`.
- **Mehrere Instanzen** = mehrere HCC-Integrationen (einer Adapter pro
  Instanz), unabhängig voneinander.

### Prometheus — template-only
- Nur **statische, validierte Query-Templates** (keine freie PromQL, kein
  Injection). Version via `/api/v1/status/buildinfo`. Label-Keys/-Values
  client-seitig gemaunt (Whitelist-Regex + Verbot von Path-Traversal
  `..`/führendem `.`). Metrik-Templates: CPU, Memory, Disk, Load (Host) +
  Container-Varianten.

### Uptime Kuma — **fixture-only, live verifizieren**
- Session-Login `POST /api/login` (JSON `username/password/remember` →
  Session-Cookie), dann `/api/monitor`. **Nur fixturbasiert getestet** —
  gegen ein reales System noch nicht verifiziert (offen).

### Docker — Zugriffs-Modell (Sicherheit)
- **Unix-Socket (lokal, empfohlen):** `extra.docker_socket` (absolut).
- **TCP + mTLS (remote, erlaubt):** `https://…:2376` mit Client-Zertifikat
  (`docker_ca`/`docker_cert`/`docker_key`).
- **Plain TCP (http) zu Nicht-Loopback: abgelehnt** (ungeschützter
  Engine-Socket = Host-Kontrolle). Loopback-TCP erlaubt, aber als hohes Risiko
  dokumentiert. Transport wird **lazig** gebaut (Zertifikatsdateien nicht bei
  jeder Policy-Prüfung geladen, `ssl.create_default_context(cafile=…)`).

---

## 3. Sicherheit

- **Kein Secret in Code/Tests/Logs:** alle Tests nutzen
  `EnvSecretsProvider` mit Fixture-Werten; echte Credentials nie.
- **Docker:** ungeschützter Remote-TCP-Socket wird hart abgelehnt
  (AGENTS.md). Read-only-Engine-API, nur GET-Endpunkte.
- **TrueNAS:** Basic nur bei inaktivem 2FA, sonst Bearer-API-Key;
  Secret-Auflösung über `SecretsProvider` (nie Klartext in Config/DB).
- **Tailscale:** Management-Key per Bearer; Local-API-Auth optional Basic.
  Local-API nur lesende Endpunkte (`status`, `whois`).
- **Prometheus:** keine freie PromQL — Label-Injection geschützt
  (Whitelist + Traversal-Verbot), Label-Filter nur client-seitig.
- **RBAC/Audit/Validierung/Fehlerhandling:** Backend-first, Adapter werfen
  die frozen `AdapterError`-Hierarchie (`ConfigError`/`AuthError`/`ApiError`/
  `TimeoutError`/`VersionError`) → sauber in API-Contract mappbar.

---

## 4. Testergebnisse (tatsächlich ausgeführt)

**Befehle (in `backend/`):**
- `uv run --extra dev pytest tests/integrations -q` → **110 passed**
- `uv run --extra dev pytest -q` (voll) → **173 passed** (63 R0-Baseline + 110 neu)
- `uv run --extra dev ruff check .` → **All checks passed**

**Neue Testmodule** (`backend/tests/integrations/`):

| Modul | # | Abgedeckte Szenarien (Auszug) |
|---|---|---|
| `test_prometheus.py` | 16 | available, not_configured, Auth-Fehler, Timeout, leere Metrik-Antwort, kaputte Werte (NaN/garbage), API-Error-Payload, Label-Injection, Discover, Historical + NaN-Skip, Alertmanager-Alerts, Whitelist |
| `test_pihole.py` | 16 | v6 (available/session-Auth/collect), v5 (pwhash/FTL-down/auth-false), Blocking `failed` ⇒ keine erfundene Metrik, Timeout, not_configured, Version-Fehler, **zwei unabhängige Instanzen** |
| `test_docker.py` | 14 | **Sicherheits-Policy** (plain-TCP-Remote rejected, Loopback, Unix-Socket, mTLS, Cert-ohne-Key), verify, discover (Host+Container, State-Mapping), collect (CPU/Memory/Net), ID-Validierung, Auth/Timeout |
| `test_tailscale.py` | 15 | api-Modus (available/auth/discover/collect), local-Modus (status/Peers/Self), Modus-Unterscheidung + Heuristik, Basic-Auth-Header, unknown-Node, Timeout |
| `test_truenas.py` | 17 | REST-v2 available + Basic/Bearer, not_configured, **Version-Gate (REST weg 26.0)**, Auth-Fehler, Timeout, Discover (**bad storage states** DEGRADED/FAULTED, SMART), Collect (Pool/Host/Disk/Dataset), unknown-Resource |
| `test_monitoring_backends.py` | 21 | Grafana (available/db-error/token-missing/datasources), Loki (ready/labels/timeout), Uptime Kuma (login/login-failure/monitors/down), **Engine** (explizit/auto-Erkennung/Delegation) |
| `test_events.py` | 9 | Severity-/Status-Mapping, Fingerprint-Stabilität (±Zeit-Drift), Minuten-Bucket, Dedup (neu vs. duplicate), LRU-Eviction |
| `test_registry_wiring.py` | 2 | App-Import registriert alle Agent-4-Adapter; instantiierbar ohne Arg |

**Fixtures** (`backend/tests/integrations/fixtures/`): `prometheus.json`,
`pihole.json`, `docker.json`, `tailscale.json`, `truenas.json`,
`grafana_loki_uptime.json`, `alertmanager.json` — klar als Fixture/Demo
gekennzeichnet, keine echten Daten.

---

## 5. Offene Punkte / Risiken

1. **Uptime Kuma + Loki nur fixturbasiert** — Login-Flow bzw. Label-Endpoint
   gegen ein reales System noch nicht verifiziert. → `needs-live-verification`.
2. **TrueNAS 25.10-Feldnamen** — Endpunkt-Tabelle basiert auf 24.04-Referenz
   (25.10-REST-Handler identisch, Plugin-Schemas nicht 1:1 diffed).
   Risiko gering; OpenAPI-Spec als Single Source of Truth nutzen.
   RAW-SMART (`smartctl -A`) ist **nicht** via REST erreichbar
   (`disk.smartctl` privat) — nur Self-Test-Resultate.
3. **Cross-Agent-Kollisionsrisiko (Agent 3 / Proxmox):**
   `backend/tests/test_adapter_interface.py` registriert einen
   `FakeAdapter` mit `kind=PROXMOX`. Wenn Agent 3 einen echten
   Proxmox-Adapter mit `kind=PROXMOX` in `app/integrations/proxmox/`
   einbindet, **stößt das auf den frozen-Registry-Konflikt**
   (`ValueError: Adapter 'proxmox' ist bereits registriert`) — **sollte bei
   Integration geklärt werden** (FakeAdapter aus dem Test nehmen, wenn ein
   echter Proxmox-Adapter lande).
4. **Home Assistant nicht implementiert** — kein eigenes Ownership-Verzeichnis
   zugewiesen; `AdapterKind.HOMEASSISTANT` bleibt `not_implemented`
   (ehrlich, kein Stub).
5. **TrueNAS-Disks laufen über `ResourceType.OTHER`** — `DISK` ist kein
   frozen `ResourceType`. Disk-Identität in `external_id`/Payload.
   Typ-Erweiterung nur per Proposal (siehe `docs/proposals/`).
6. **Persistenter Event-Store + REST-Ausbaustufe blockiert** —
   Adapter-Ebene ist heute nur programmatisch (Registry) erreichbar, nicht
   per REST. Vorschlag in `docs/proposals/agent4-monitoring-api.md`.

---

## 6. Betroffene Dateien

**Geändert:**
- `backend/app/integrations/__init__.py` (guarded Subpackage-Imports)

**Neu (Agent 4):**
- `backend/app/integrations/monitoring/` — `base.py`, `engine.py`,
  `prometheus.py`, `grafana.py`, `loki.py`, `uptime_kuma.py`, `events.py`,
  `httputil.py`, `__init__.py`
- `backend/app/integrations/pihole/` — `adapter.py`, `__init__.py`
- `backend/app/integrations/docker/` — `adapter.py`, `security.py`, `__init__.py`
- `backend/app/integrations/tailscale/` — `adapter.py`, `__init__.py`
- `backend/app/integrations/truenas/` — `adapter.py`, `__init__.py`
- `backend/tests/integrations/` — `conftest.py`, 8 Testmodule, `fixtures/*.json`
- `docs/proposals/agent4-monitoring-api.md`
- `docs/agent-reports/R1-telemetry.md` (dieses Dokument)

**Nicht angefasst (Contract-Integrität):** `backend/app/contracts/**`,
`backend/alembic/**`, `backend/app/adapters/**` (frozen), `backend/app/models/**`
(frozen Enums).

---

## 7. Commit-Hash

**Commit:** `9ae91e8`  ·  **Branch:** `feature/telemetry`  ·  **kein Merge nach `main`**

(Hinweis: Das Commit-Hash in diesem Dokument bezieht sich auf den
Commit, der dieses Dokument enthält — nach Finalisierung des Hashes wurde
der Commit per `git commit --amend` geschlossen; nur auf dem eigenen,
nicht gepushten Branch `feature/telemetry`.)
