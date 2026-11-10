# HCC 2.0 — API-Contracts (R0, frozen)

**Verbindliche Quelle:** [`backend/contracts/openapi.v1.json`](../backend/contracts/openapi.v1.json)
(generiert über `scripts/generate-openapi.py`). Der Snapshot-Test
`backend/tests/test_contracts_snapshot.py` stellt sicher, dass Code und
Snapshot identisch sind.

## 1. Grundregeln

- **Versionierung:** alle Endpoints unter `/api/v1/`. Breaking Changes nur
  in `/api/v2/` (mit Migration).
- **Authentifizierung:** serverseitige Session via Cookie
  `hcc_session` (HttpOnly, SameSite=Lax, Secure in Produktion). Kein
  Bearer-Token, keine JWTs.
- **CSRF (Double-Submit):** state-aendernde Requests (POST/PUT/PATCH/DELETE)
  unter `/api/v1/` müssen den Header `X-CSRF-Token` mit dem exakten Wert
  des Cookies `hcc_csrf` (nicht HttpOnly) setzen. Exemption:
  `POST /auth/login`, `POST /auth/bootstrap`.
- **Zeitstempel:** immer UTC, ISO-8601 mit Offset.
- **Fehlende Daten:** `unknown` / `null` / `not_configured` — niemals
  Zufalls- oder Erfolgswerte.
- **Zustände (fachlich getrennt):** `healthy | degraded | down | unknown | not_configured`.
- **Paging:** alle Listen-Endpunkte akzeptieren `page` (≥1) und
  `page_size` (1–200) und antworten mit der `Paged_*`-Envelope.

## 2. Error-Envelope (frozen)

Alle Fehlerantworten (auch 4xx) haben exakt diese Form:

```json
{
  "error": {
    "code": "maschinell_lesbar",
    "message": "menschenlesbar, ohne Secrets/Stacktraces",
    "details": null,
    "request_id": "uuid"
  }
}
```

| HTTP | `code`                     | Bedeutung                          |
| ---- | -------------------------- | ---------------------------------- |
| 401  | `unauthenticated`          | keine/gültige Session fehlt        |
| 403  | `forbidden`                | RBAC oder CSRF abgelehnt           |
| 404  | `not_found`                | Ressourcen/Endpunkt unbekannt      |
| 422  | `validation_error`         | Pydantic-Validierung gescheitert (`details.errors[]`) |
| 500  | `internal_error`           | unerwarteter Fehler (Details nur in Logs) |
| 501  | `not_implemented`          | Adapter für Integration fehlt (R0) |

Weitere Codes: `conflict` (409), `rate_limited` (429),
`method_not_allowed` (405) — siehe `app/errors.py::ErrorCode`.

## 3. Paging-Envelope (frozen)

```json
{ "items": [...], "page": 1, "page_size": 50, "total": 123, "total_pages": 3 }
```

## 4. Endpunkt-Verzeichnis (R0-frozen Routenplan)

| Methode | Pfad | Berechtigung | Beschreibung |
| ------- | ---- | ------------ | ------------ |
| GET  | `/api/v1/health/live`  | öffentlich | Live-Check (systemd); immer 200, wenn API antwortet |
| GET  | `/api/v1/health/ready` | öffentlich | Readiness inkl. DB; 503 bei `status != ok` |
| GET  | `/api/v1/version`      | öffentlich | Version/Release/Commit |
| POST | `/api/v1/auth/bootstrap` | öffentlich (einmalig) | Erst-Admin; nur wenn keine User existieren + `HCC_BOOTSTRAP_TOKEN` (konstanter Zeitabgleich); setzt `must_change_password` |
| POST | `/api/v1/auth/login`   | öffentlich (Rate-Limit) | setzt `hcc_session` + `hcc_csrf`-Cookies |
| POST | `/api/v1/auth/logout`  | authed + CSRF | Session widerrufen |
| GET  | `/api/v1/auth/me`      | authed       | aktuelle User-Infos (inkl. Rolle) |
| GET  | `/api/v1/users`        | admin (`users.manage`) | User-Liste (paged) |
| POST | `/api/v1/users`        | admin + CSRF | User anlegen |
| PATCH| `/api/v1/users/{user_id}` | admin + CSRF | User ändern (Rolle/Name/aktiv); letzter Admin-Schutz |
| GET  | `/api/v1/integrations` | viewer+ (`integrations.read`) | Integrationen (paged); **keine Secret-Werte** (nur `secret_ref`) |
| GET  | `/api/v1/integrations/{integration_id}` | viewer+ | Detail (Slug `integration_id`) |
| PUT  | `/api/v1/integrations/{integration_id}` | admin + CSRF (`integrations.manage`) | konfigurieren (`adapter`, `base_url`, `secret_ref`) |
| POST | `/api/v1/integrations/{integration_id}/verify` | admin + CSRF | Adapter-Registry abfragen; R0: `501 not_implemented` (Registry leer) |
| DELETE| `/api/v1/integrations/{integration_id}` | admin + CSRF | Integration löschen (Kaskade über Ressourcen) |
| GET  | `/api/v1/resources`    | viewer+ (`resources.read`) | Inventar (paged, Filter `status`, `resource_type`) |
| GET  | `/api/v1/resources/{resource_id}` | viewer+ | Detail inkl. Beziehungen |
| GET  | `/api/v1/audit`        | admin (`audit.read`) | Audit-Events (paged, append-only) |

RBAC-Modell: `viewer < operator < admin`; zentrale Berechtigungen in
`backend/app/auth/rbac.py` (stabile Keys, frozen).

## 5. Wichtige Schemas (Auszug)

- `IntegrationCreate/Update`: `integration_id` (3–64, `^[a-z0-9][a-z0-9-]*$`),
  `adapter` (Enum `proxmox|truenas|pihole|tailscale|docker|monitoring|homeassistant|unknown`),
  `base_url` (HTTP(S)), `secret_ref` (Name, **keine Werte**).
- `ResourceOut`: Identität `(integration_id, resource_type, external_id)`;
  `status ∈ {healthy, degraded, down, unknown, not_configured}`;
  `source ∈ {api, manual, inferred}`; `payload` frei, aber ohne Secrets.
- `VerifyResponse`: `status ∈ {ok, error, not_implemented}`,
  `state` (stabil aus `AdapterState`), `message` ohne Secrets.
- `AuditEventOut`: `id`, `username` (redundant, bleibt nach User-Loeschung),
  `action`, `resource_type/id`, `ip_address`, `user_agent`, `details`
  (maskiert), `created_at` (UTC).

## 6. Änderungsprozess (Pflicht)

1. `docs/proposals/<agent>-<topic>.md` (Motivation, Diff, Impact).
2. Blocken der betroffenen Funktion, bis reviewed (AGENTS.md Regel 4).
3. Gezielte Änderung in `backend/app/contracts/` (+ Routen bei Bedarf).
4. `uv run python scripts/generate-openapi.py` → Snapshot regenerieren.
5. Review des Diffs von `backend/contracts/openapi.v1.json`.
6. Eintrag in diesem Dokument (Tabelle 4 + Schemas bei Änderung).

## 7. Frontend-Client-Generierung

```bash
# aus frontend/ (Node >= 20.19)
npx openapi-typescript ../backend/contracts/openapi.v1.json -o src/api/generated/schema.ts
```

Die generierten Typen in `frontend/src/api/generated/` sind für Agent 2
**nur lesbar** — Änderungen ausschließlich über §6.
