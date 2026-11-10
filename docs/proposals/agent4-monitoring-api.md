# Vorschlag: REST-Ausbaustufe für Monitoring-/Telemetrie-Endpunkte (Agent 4, R1)

**Status: BLOCKED — Vorschlag, nicht implementiert** (AGENTS.md Regel 4: keine
stillschweigende Änderung an eingefrorenen Contracts; REST-Contract
`backend/contracts/openapi.v1.json` ist eingefroren).

Agent 4 (Monitoring & Integrations, Branch `feature/telemetry`) hat die
Adapter-Ebene (`app/integrations/*`) fertig implementiert. Diese ist über das
frozen `IntegrationAdapter`-Protokoll (`app/adapters/base.py`) und die
Registry aufrufbar, aber **bewusst nicht per REST exponiert** — der eingefrorene
Contract enthält nur:

- `GET /api/v1/integrations` (paged)
- `GET /api/v1/integrations/{integration_id}`
- `PUT /api/v1/integrations/{integration_id}` (Konfiguration)
- `POST /api/v1/integrations/{integration_id}/verify`
- `DELETE /api/v1/integrations/{integration_id}`

## Was die Adapter-Ebene heute kann (ohne REST)

Jeder registrierte Adapter (`monitoring`, `pihole`, `docker`, `tailscale`,
`truenas`) implementiert:

- `verify(config, secrets)` → Erreichbarkeit + API-Version
- `capabilities(config, secrets)` → Feature-Liste (version-/capability-gated)
- `discover(config, secrets)` → `AsyncIterator[ResourceRecord]` (Inventory)
- `collect(config, secrets, resource_type, external_id)` → `MetricsRecord`
  (Aktuelle Metriken mit Einheiten)
- `events(config, secrets)` / `alerts(config, secrets)` →
  `AsyncIterator[NormalizedEvent]` / `AsyncIterator[NormalizedAlert]`
  (einheitliches Event-Modell, Deduplication via `EventDeduplicator`)
- Monitoring-Backends zusätzlich: `historical_metrics(metric, labels, range)`
  für 1h/6h/24h/7d/30d und `host_availability`/`service_availability`

## Vorgelegte Endpunkte (für die Contract-Entscheidung des Backbones)

Vorschlag einer R2-Ausbaustufe. Alle Endpunkte sind **read-only** und
nutzen die bestehenden `ResourceRecord`/`MetricsRecord`-Modelle — keine neuen
Domain-Modelle nötig.

| Methode | Pfad | Purpose | ACL (Vorschlag) |
|---|---|---|---|
| POST | `/api/v1/integrations/{id}/discover` | Discovery auslösen; legt/updatet `ResourceRecord`s | admin + CSRF (`integrations.manage`) |
| GET | `/api/v1/resources` | Entdeckte Ressourcen (paged, filter: `type`, `status`) | viewer+ (`resources.read`) |
| GET | `/api/v1/resources/{resource_id}/metrics` | Aktuelle Metriken (`collect`) | viewer+ |
| GET | `/api/v1/resources/{resource_id}/metrics/history` | Historische Metriken (params: `metric`, `range=1h\|6h\|24h\|7d\|30d`, `labels`) | viewer+ |
| GET | `/api/v1/resources/{resource_id}/availability` | Erreichbarkeitsstatus (Prometheus `up`/Uptime Kuma/Docker State) | viewer+ |
| GET | `/api/v1/events` | Normalisierte Events/Alerts (paged, filter: `severity`, `status`, `source`) | viewer+ |
| POST | `/api/v1/integrations/{id}/collect` | Gezieltes Sampln einer bekannten Resource | admin + CSRF (vermeidet Polling-Last) |

## Persistenter Event-Store (offen)

Die Adapter liefern Events/Alerts als **Ephemere-Iteratoren**. Für
historische Auswertung, Deduplication über Neustarts hinweg und
Alerting-Verarbeitung braucht es einen persistenten Store. Optionen:

1. **Neue Tabelle `events`** (eigenes Alembic-Migration-Paket) — Schema:
   `id`, `source`, `source_event_id`, `event_type`, `severity`, `status`,
   `message`, `resource_type`, `external_id`, `occurred_at`, `received_at`,
   `fingerprint` (unique, aus `event_fingerprint()`). Deduplication läuft
   dann über `fingerprint`.
2. **Externe Quelle** (Loki/Alertmanager direkt) — reduziert HCC-Last,
   aber braucht ein dediziertes Read-Modell und die Adapter-Anteile wären
   dann nur Normalisierer, nicht Speicher.

**Empfehlung:** Option 1, da sie deterministisch ist, ohne externe
Abhängigkeit bleibt, und die Normalisierung (`normalize_event`,
`event_fingerprint`, `EventDeduplicator`) schon in
`app/integrations/monitoring/events.py` implementiert und getestet ist.

## Blockierte Funktionen

Bis der Contract entschieden ist:

- Keine REST-Endpunkte für discover/metrics/events — die Adapter-Ebene ist
  nur programmatisch (per Registry) erreichbar.
- Kein persistenter Event-Store (Migration blockiert).
- Alerting-Integration (Webhook/Notification) ist nicht implementiert —
  das wäre eine eigene Ausbaustufe mit eigener Entscheidung
  (Webhook-Ziel, Escalation, Stummzeiten).

## Abhängigkeiten / Offene Fragen

- `ResourceType` ist frozen (fünfeinhalb Mitglieder, **kein `DISK`**).
  TrueNAS-Disks laufen daher über `ResourceType.OTHER`
  (Disk-Identität in `external_id`/Payload). Typ-Erweiterung nur per
  separatem Proposal.
- Die `verify`-Endpunkte (bestehend) sind die einzigen, die die Adapter
  heute über REST erreichen — für alles andere braucht es die obige
  Ausbaustufe.
- `POST /discover` und `POST /collect` sollten Rate-Limiting bzw.
  Job-Queue-Verhalten erhalten, bevor sie produktiv werden
  (keine synchrone Langzeit-Aufrufe in Request-Handling).
