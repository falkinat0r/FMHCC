# Vorschlag: Passwort-Änderungs-Endpunkt (Agent 1, R1)

- **Status:** offen (Feature blockiert, bis Freigabe vorliegt)
- **Autor:** Agent 1 (backend-auth), Branch `feature/auth`
- **Betroffener Bereich:** `backend/contracts/openapi.v1.json` (frozen, R0), `docs/api-contracts.md`, `backend/app/api/v1/auth.py`, `backend/app/users/service.py`, Frontend-Client (Agent 2)
- **Verletzte Regel:** keine — dieser Vorschlag existiert, weil das Feature **ohne** Contract-Änderung nicht vollständig implementierbar ist (AGENTS.md §4)

## 1. Problem

R1 verlangt, dass ein User sein eigenes Passwort ändern kann (z. B. nach
`must_change_password` beim ersten Login, bei Rotation). Der R0-frozen
OpenAPI-Contract (`backend/contracts/openapi.v1.json`) enthält **keinen**
Endpunkt dafür:

- `/api/v1/users` (GET/POST) — Verzeichnis/Erstellung (Admin)
- `/api/v1/users/{user_id}` (PATCH, `UserUpdate`) — Admin-Update
  (kein Passwortfeld; Passwort darf administrativ nicht gesetzt werden)
- `/api/v1/auth/*` — nur `bootstrap`, `login`, `logout`, `me`

Ein Eigen-Endpunkt wäre eine **Contract-Erweiterung** und daher nur über
diesen Vorschlag zulässig.

## 2. Was in R1 bereits (blockiert) implementiert ist

Die Logik ist fertig, getestet und produktionsreif im Service-Layer:

- `app/users/service.py::change_password(db, user, *, current_password, new_password)`
  - verifiziert das aktuelle Passwort (Argon2id) → sonst `401 unauthenticated`
  - validiert das neue Passwort nach denselben Regeln wie bei der Erzeugung
  - lehnt `current == new` mit `422 validation_error` ab
  - setzt `must_change_password = false`
  - **widerruft alle bestehenden Sessions des Users**
  - auditet `auth.password_changed` (ohne Passwortwerte, nur `sessions_revoked`)
- Unit-Tests: `backend/tests/auth/test_password_change.py`

**Nicht implementiert (bewusst):** der API-Endpunkt. Bis zur Freigabe gibt
es dazu keinen Route-Eintrag und keinen Schema-Zusatz; das Snapshot-Test
`tests/test_contracts_snapshot.py` bleibt grün.

## 3. Vorgeschlagener Contract-Zusatz

Neuer Endpunkt (Routenplan-Extension, `openapi.v1.json` +
`scripts/generate-openapi.py` neu generieren):

```
POST /api/v1/auth/change-password
```

Request (neues Schema `PasswordChangeRequest`):

```json
{
  "current_password": "min 10, max 200 Zeichen",
  "new_password": "min 10, max 200 Zeichen"
}
```

Responses:

| HTTP | `code`             | Bedeutung                                          |
| ---- | ------------------ | -------------------------------------------------- |
| 200  | —                  | ok, alle Sessions des Users widerrufen             |
| 401  | `unauthenticated`  | keine Session oder aktuelles Passwort falsch       |
| 422  | `validation_error` | neues Passwort zu kurz/identisch mit altem         |
| 429  | `rate_limited`     | Limit getroffen (gleicher Limiter wie Login)       |

Zusätzliche Regeln:

- **RBAC:** alle Rollen (viewer/operator/admin), aber ausschließlich das
  eigene Passwort — keine Delegation, kein Admin-Reset über diesen Pfad.
- **CSRF:** state-changing POST unter `/api/v1/` → CSRF-Token Pflicht
  (gleiche Middleware wie alle anderen POST).
- **Session:** der aktiven Session wird ein Fingerprint zugewiesen, der bei
  jeder Passwort-Änderung rotiert (alle Alt-Cookies ungültig).
- **Audit:** `auth.password_changed`, `actor` = der User selbst,
  `resource_type=user`, ohne Passwortwerte.

## 4. Alternativen (bewusst verworfen)

1. **`UserUpdate` um `password` erweitern** → verworfen:
   - `PATCH /api/v1/users/{user_id}` ist Admin-orientiert (RBAC admin);
     ein Selbst-Service-Pfad dort wäre semantisch falsch.
   - Ändert ein **bestehendes** frozen Schema (größere Auswirkung als ein
     neuer Endpunkt).
   - Admin-Reset durch Admin wäre zusätzlich ein Sicherheitsrisiko
     (Keine Passwort-Übermittlung über Admin-Pfad).
2. **Separater Endpunkt `PATCH /api/v1/users/me/password`** → verworfen:
   - `me` ist bereits ein GET-Endpunkt; ein eigener `change-password` unter
     `/api/v1/auth/` ist konsistenter mit dem bestehenden Auth-Routenplan.

## 5. Auswirkungen der Freigabe

- `backend/contracts/openapi.v1.json` wird erweitert (neuer Pfad + Schema),
  `docs/api-contracts.md` entsprechend aktualisiert.
- `tests/test_contracts_snapshot.py` muss das neue Snapshot mitnehmen.
- Agent 2 (Frontend) kann den generierten Client erweitern und eine
  Einstellungen-/Passwort-Seite bauen.
- Agent 5 (QA/Security) ergänzt Contract-/E2E-Tests.
- Keinerlei Änderung an `backend/alembic/**` oder am Datenmodell.

## 6. Entscheidung

- [ ] Freigabe: neuer Endpunkt `POST /api/v1/auth/change-password`
- [ ] Ablehnung: Feature bleibt auf Service-Ebene (nur interne Nutzung),
      Frontend baut kein UI dafür
- [ ] Ablehnung mit Alternativform (bitte spezifizieren)

Freigabe durch: Integrationsreview (alle Agenten / Koordination), da
Contract-Änderung.
