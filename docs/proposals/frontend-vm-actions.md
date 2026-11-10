# Proposal: VM-/LXC-Verwaltungsaktionen (Agent: frontend)

**Status:** offen — betroffene UI-Funktion ist blockiert (kein Endpunkt, keine
alternativen Wege).
**Betreff:** `/api/v1` enthält keine Endpunkte für VM-/LXC-Aktionen, obwohl das
RBAC-Modell die Rolle `operator` („Lesen + Aktionen") definiert.

## Motivation

- Das frozen RBAC-Modell (`viewer < operator < admin`) sieht `operator` als
  rollenbasierten „Operator (Lesen + Aktionen)" vor — ohne Aktions-Endpunkte
  ist die Rolle funktional identisch mit `viewer`.
- Die MASTER_PROMPT-Vorgaben verlangen VM-/LXC-Verwaltung (Start, sanftes
  Shutdown, Reboot) aus dem Control Center.
- Die UI zeigt die Aktionsknöpfe rollenabhängig (operator+), aber der
  Bestätigungs-Dialog bleibt im R0-Vertrag ehrlich blockiert
  (`frontend/src/features/compute/ActionDialog.tsx`,
  `endpointAvailable={false}`). Es werden **keine** alternativen Wege erzeugt
  (AGENTS.md Regel 7/8).

## Vorschlag (Diff-Plan)

Neue Pfade (Routenplan-Erweiterung):

| Methode | Pfad | Berechtigung | Beschreibung |
| ------- | ---- | ------------ | ------------ |
| POST | `/api/v1/resources/{resource_id}/actions/{action}` | operator+ + CSRF (`resources.act`) | Aktion `start` \| `stop` \| `reboot`; nur für `resource_type ∈ {vm, lxc}`; auditiert; asynchron (Job-Id im Response-Body) |

Schemata (neue Schemas im OpenAPI-Snapshot):

- `ResourceActionRequest`: `{ action: "start"|"stop"|"reboot", confirm: true }`
  (explizite Bestätigung, damit UI-Dialog und Audit übereinstimmen).
- `ResourceActionResponse`: `{ job_id: uuid, status: "accepted" }` —
  Bestätigung nur „angenommen", **nicht** „erledigt" (Erfolgswerte nicht
  erfinden, AGENTS.md §7).
- Fehler-Codes: `409 conflict` (Ressource bereits in Zielzustand/in Aktion),
  `422 validation_error` (falscher Resource-Typ).

Voraussetzungen (Backend):
- Job-/Status-Begriff für asynchrone Aktionen (z. B. `GET /jobs/{job_id}` oder
  Status-Überprüfung über `GET /resources/{resource_id}` — bevorzugt Letzteres,
  da der Ressourcen-Status ohnehin 1:1 aus der Integration stammt).
- Proxmox-Adapter implementiert die Aktionen **über die Proxmox-API**
  (`/api2/json/nodes/{node}/qemu/{vmid}/status/start` bzw. `shutdown`/`reboot`,
  LXC analog) — niemals über SSH.

## Impact

- **Frontend:** `ActionDialog` schaltet auf `endpointAvailable=true` um, sobald
  der Endpunkt existiert; der Client-Code (`src/api/query.ts`) wird um
  `useResourceAction` ergänzt (Mutation, CSRF-Header setzt der Client bereits
  generisch).
- **RBAC:** neue Berechtigungs-Key `resources.act` (operator+).
- **Audit:** `action="resource.action.<action>"`, `resource_type="vm"|"lxc"`.
- **Security:** CSRF-pflichtig (state-aendernd), Rate-Limit wie Login,
  Bestätigung im Payload (`confirm: true`) gegen versehentliche Aufrufe.
