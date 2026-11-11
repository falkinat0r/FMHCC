# Vorschlag Agent 3: Proxmox-Adapter — Core-Integration & R2-Endpunkte

Status: Offen (keine Blockade — R1-Funktionalität läuft ohne diese Punkte,
der Verify-Endpunkt antwortet dann ehrlich mit `not_implemented`)
Betrifft: Core (main.py / api/v1 / Migrations) — Agent 3 ändert diese Dateien NICHT.

## Kontext

Der Proxmox-Adapter (R1, `app/integrations/proxmox/`) ist fertig und gegen
`httpx.MockTransport` voll getestet. Die Registry-Registrierung erfolgt
bewusst EXPLIZIT (`register_proxmox_adapter()`), damit die eingefrorene
R0-Registry-Testbasis (FakeAdapter, kind=proxmox) keine Kollision erzeugt.
Damit die Registry in Produktion nicht leer bleibt, braucht es einen
Core-Hook. Zusätzlich fehlen für den vollen Betrieb zwei R2-Endpunkte
und ein Konfigurations-Persistierungsweg.

## 1. Produktions-Registrierung (Blocker für Verify in Production)

**Vorschlag:** Neuer Core-Datei `backend/app/integrations/bootstrap.py`:

```python
"""Adapter-Registry-Bootstrap (Core, R2)."""
from app.integrations.proxmox.adapter import register_proxmox_adapter

def register_all_adapters() -> None:
    register_proxmox_adapter()  # weitere Agenten: hier erweitern
```

Aufruf einmalig in `create_app()` (vor Router-Registrierung) oder in der
Lifespan. Alternativ: Aufruf in `app/integrations/registry.py`-Module
eines neuen Imports — der Bootstrap-Modul-Ansatz wird bevorzugt, weil
er die Imports der Adapter aus dem API-Pfad heraushält.

Bis dahin: `POST /integrations/{id}/verify` antwortet mit
`status: "not_implemented"` und `message` "Kein Adapter für 'proxmox'
in diesem Build registriert" — ehrlich, kein Stub (frozen R0-Verhalten).

## 2. R2-Endpunkt: Inventar-Sync (Discover → upsert_resources)

**Vorschlag:** `POST /api/v1/integrations/{integration_id}/sync`

- RBAC: NEUER Permission-Key `inventory.sync` (Rolle OPERATOR).
  Grund: Sync schreibt ins Inventar (nicht read-only) — `integrations.read`
  wäre zu lax, `actions.run` semantisch falsch. Neue Keys nur per Proposal
  (RBAC-Regel) — dieses Dokument ist das Proposal.
- Ablauf: Registry-Aufschlüsselung → `adapter.discover(config, secrets)` →
  `sync_proxmox_inventory(db, integration=..., records=...)` →
  Audit-Event `integrations.sync` mit `SyncResult`-Details →
  HTTP 200 `{"synced": {"total": n, "created": n, "updated": n,
  "relations_created": n}}`.
- Fehler: AdapterError → Error-Envelope mit `adapter_error`-Semantik
  (frozen), Integration.status=`error`, `last_error` gesetzt.
- Zeitlimit: Discover-Requests pro Node sind rate-limitet (Client);
  Endpunkt sollte `timeout_seconds` aus der Integration übernehmen.

## 3. R2-Endpunkt: Compute-Aktionen mit Idempotenz-Key

**Vorschlag:** `POST /api/v1/integrations/{integration_id}/actions`

- Body: `{"action": "start|shutdown|reboot", "external_id": "101",
  "confirmed": true}` + Header `Idempotency-Key` (optional; ohne Key
  wird serverseitig ein UUID-Key erzeugt → immer neuer Job,
  mit Key → Replay-Idempotenz, frozen ActionJob-Schema).
- RBAC: frozen Key `actions.run` (OPERATOR+) — bereits in
  `execute_compute_action()` serverseitig geprüft.
- Bestätigung: `confirmed` zwingend (422 ohne Bestätigung) —
  implementiert in `app/integrations/proxmox/actions.py`.
- Antwort: ActionJob (id, status, details) — Status `succeeded` bedeutet
  "Proxmox-Akzeptierung (UPID)", NICHT "abgeschlossen" (async-Task;
  Polling-Endpunkt `/actions/{job_id}` mit Task-Status wäre R2-Folgeaufgabe).
- Audit: erfolgt in `execute_compute_action` (`actions.compute.<verb>`,
  `.accepted`/`.failed`/`.replay`).

## 4. Konfigurations-Persistierung (TLS-/Rate-Limit-Optionen)

Der frozen Verify-Endpunkt setzt nur `base_url` + `secret_ref` in die
`AdapterConfig`; `extra` bleibt leer. Die Proxmox-Optionen
(`tls_ca_bundle`, `tls_verify_disabled`, `rate_limit_per_second`,
`max_retries`, `retry_backoff_seconds`, `fetch_resource_details`) sind
derzeit nur über direkte Adapter-Aufrufe setzbar.

**Vorschlag (empfohlen):** Neue JSON-Spalte `options` (default `{}`) auf
`integrations` via Migration (Core-besitzt) + `IntegrationCreate.options:
dict[str, str]` (nur String-Werte, gefiltert auf erlaubte Keys pro
Adapter-Kind). Die Endpunkte bauen `AdapterConfig.extra` daraus.

**Alternative (weniger Aufwand, weniger sauber):** Globale Env-Variablen
`HCC_PROXMOX_TLS_CA_BUNDLE`, `HCC_PROXMOX_TLS_VERIFY_DISABLED` etc. in
`secrets.env`/`settings` — aber nicht pro Integration, und `extra` wäre
bei API-Aufrufen trotzdem leer (doppelter Pfad).

**Sicherheit (beide Varianten):** `tls_verify_disabled` bleibt ein
explizites, WARNING-ge-loggtes Opt-in (Default `verify=True`);
keine Blanket-Abschaltung, CA-Bundle-Pfad wird nicht in API-Antworten
wiedergegeben (nur Referenz).

## 5. Status-Mapping-Entscheide (zur Kenntnis, kein Core-Aufwand)

Dokumentiert im Report `docs/agent-reports/R1-proxmox.md`:
running→healthy, paused→degraded, stopped→down; Node offline→down,
maintenance→degraded, online+quorum_ok=false→degraded.

## Offene Risiken / Voraussetzungen

- Item 1 (Bootstrap) ist der einzige Blocker für den
  Verify-Endpunkt in Produktion; Items 2–4 sind R2-Funktionalität.
- Kein Contract-Bruch: keine neuen Endpunkte ohne frozen Routenplan-Update
  (`docs/api-contracts.md` + OpenAPI-Snapshot) — das gehört zum R2-Core.
