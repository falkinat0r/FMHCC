# R1 — Security Findings (QA, Agent 5)

Stand: 2026-11-10 · Branch `feature/qa`

Methodik: Code-Review (Auth/Sessions/RBAC/Input/Audit) + ausgeführte
Regressionstests unter `tests/security/`. Jede Findung trägt Severity,
Reproduktionsweg und Empfehlung. Schweregrad: **kritisch / hoch / mittel /
niedrig / info**.

> Wichtig: Alle Findungen sind aus R0-Code. R1 ändert Produktcode bewusst
> nicht (QA-Scope) — diese Doku ist die Grundlage für die R1/Fix-Priorität.

## S1 — Audit-Log verliert FK auf neu angelegte Integration — **mittel**

- **Wo:** `backend/app/api/v1/integrations.py::upsert_integration` (Z. 104–122)
- **Was:** `record_audit(..., integration_id=integration.id)` (Z. 119) wird
  **vor** `db.flush()` (Z. 122) aufgerufen. Bei einer *neuen* Integration
  ist `integration.id` noch `None` → die Audit-Zeile `integrations.configure`
  referenziert keine Integration (FK `null`). Die Handlung ist nachvollziehbar,
  aber die Zuordnung zur Ressource fehlt.
- **Reproduktion:** Admin-Session, `PUT /api/v1/integrations/proxmox-1` für eine
  noch nicht existierende Integration → Audit-Zeile `integrations.configure`
  mit `integration_id = NULL`.
- **Empfehlung:** Erst `db.flush()` (ID-Backfill), dann `record_audit`. Alternativ
  `integration_id` (Slug) als `details` mitschreiben (ist bereits in `details`).
  Geringer Aufwand, keine Contract-Änderung.

## S2 — 405 wird als `not_found` codiert, Doc verspricht `method_not_allowed` — **niedrig**

- **Wo:** `backend/app/errors.py::_STATUS_CODE_MAP` (Z. 56) vs.
  `docs/api-contracts.md` (Z. 51) + `ErrorCode`-Enum.
- **Was:** Das Dokument verspricht einen stabilen Code `method_not_allowed`
  (405). Der Enum hat ihn nicht; das Mapping führt 405 auf `not_found` zurück.
  Konsument, der auf `method_not_allowed` filtert, findet 405-Fälle nicht.
- **Reproduktion:** `POST /api/v1/health/live` (nur GET erlaubt) → HTTP 405 mit
  `error.code = "not_found"`.
- **Empfehlung:** Entweder `method_not_allowed` in `ErrorCode` aufnehmen und
  Mapping setzen (Contract-Änderung → R1-Vorschlags-Prozess, siehe
  `docs/proposals/`), oder die Doku korrigieren. Bis dahin: Consumer sollen
  auf den HTTP-Status, nicht den Code, achten.

## S3 — Login-Rate-Limit pro IP, aber hinter nginx nur ein Bucket — **mittel**

- **Wo:** `backend/app/api/v1/auth.py::_login_limiter` (Z. 38, 91) +
  `client_ip` (Z. 50).
- **Was:** `SlidingWindowLimiter(max_calls=10, window=60s)` wird pro
  `request.client.host` geschlüsselt. Hinter dem Loopback-nginx (Proxy) ist
  `request.client.host` regelmäßig `127.0.0.1` → **alle** Logins teilen sich
  EIN 10-Requests/min-Bucket. In Produktion mit mehreren Admins kann ein
  normaler Login-Alltag den Lockout anderer auslösen (DoS auf sich selbst);
  für echten Brute-Force-Schutz isoliert es nicht, da die echte Client-IP
  nicht aus `X-Forwarded-For` abgeleitet wird.
- **Reproduktion:** Über nginx 11x `POST /api/v1/auth/login` in 60 s → 11.
  Versuch `429`, unabhängig vom eigentlichen Absender.
- **Empfehlung:** In Produktion die echte Client-IP aus dem vertrauenswürdigen
  Proxy-Header (`X-Forwarded-For`) ableiten (nur wenn `request.client.host`
  Loopback ist) und/oder Rate-Limit auf ein geteiltes Backing (z. B.
  Datenbank) auslagern. Mind. Doku-Vermerk, dass in-memory-Limit
  Single-Instance-/Loopback-Annahme ist.

## S4 — `SessionService.resolve` prüft `is_active` nicht — **niedrig (abgemildert)**

- **Wo:** `backend/app/auth/sessions.py::resolve` (Z. 72–83).
- **Was:** `resolve()` gibt den `User` zurück, wenn Session nicht widerrufen
  und nicht abgelaufen ist. Es prüft **nicht** `user.is_active`. Ein
  deaktivierter Nutzer könnte damit eine gültige Session halten.
- **Abmilderung:** Alle geschützten Endpunkte laufen durch
  `require_permission` → `rbac.py:50`, das `user.is_active` **pruft** →
  deaktivierter User erhält dort `401`. Deshalb kein aktiver Exploit-Pfad.
- **Reproduktion:** Admin deaktiviert Viewer (`PATCH /api/v1/users/{id}`,
  `is_active=false`) → Viewer-Session liefert trotzdem bei `/auth/me`
  Daten, aber bei geschützten Schreib-/Lesendpoints `401`.
- **Empfehlung:** `is_active`-Check als Defensive-In-Depth in `resolve()`
  nachziehen (Return `None` wenn inaktiv), damit nicht nur die RBAC-Schicht
  die Quelle der Wahrheit ist. Geringer Aufwand.

## S5 — LIKE-Wildcards in `q`/`action`-Filtern — **niedrig**

- **Wo:** Audit-/User-Listefilter (Suchparameter `q`, `action`).
- **Was:** Suchwerte fließen in `LIKE`-Muster. `parameterized` → **kein SQLi**.
  Jedoch sind `%`/`_` im Suchwert nicht maskiert → ein Nutzer kann mit `%`
  die volle Ergebnismenge erzwingen (mildes DoS/Information-Leak im
  paginierten Rahmen).
- **Reproduktion:** `GET /api/v1/audit?q=%` → liefert alle Zeilen (paginiert).
- **Empfehlung:** `%`/`_` in Benutzereingaben escapen (z. B. `ESCAPE '\'`) oder
  `q`-Länge/Charaktere begrenzen. Gering.

## S6 — ESLint 9 EOL-Deprecation-Warnung — **info**

- **Wo:** `frontend/package.json` (eslint 9) — bei `npm run lint` erscheint
  eine Deprecation-Hinweiszeile.
- **Was:** Funktionell unkritisch; Hinweis auf zukünftige Breaking Change.
- **Empfehlung:** Beim nächsten Frontend-Release ESLint-Major bewusst updaten.

## S7 — Frontend-Client setzt bei POST ohne Body keinen `Content-Type` — **info**

- **Wo:** `frontend/src/api/client.ts` (POST ohne Body).
- **Was:** Bewusstes, dokumentiertes Verhalten (kein unnötiger Header für
  leere Body). R0-Test hatte es fälschlich erwartet; QA-Test korrigiert.
- **Empfehlung:** Keine Änderung. Dokumentiert.

## S8 — TestClient pro-Request-`cookies` nicht unterstützt — **info (Test-Tooling)**

- **Wo:** `tests/security/*` (Starlette `TestClient`).
- **Was:** `TestClient.post(..., cookies=...)` wird in dieser Version
  ignoriert/deprekiert → QA-Tests verwenden isolierte Fixture-Clients mit
  eigenem Cookie-Jar. Kein Produkt-Problem, rein Test-Tooling.
- **Empfehlung:** Fixture-Muster (eigener `TestClient` pro Rolle) beibehalten.

## S9 — Kein `package-lock.json` (Reproduzierbarkeit) — **niedrig**

- **Wo:** `frontend/` (kein Lockfile im Repo).
- **Was:** Frontend-Abhängigkeiten sind ohne Lockfile nicht exakt
  reproduzierbar; Builds können sich bei transitive Updates verschieben.
- **Empfehlung:** `npm install` einmalig ausführen und `package-lock.json`
  committen; CI dann `npm ci`. Bis dahin bleibt CI bei `npm install`.

## S10 — Secret-Scanner (neues Tool) — **info (Kontrolle, nicht Befund)**

- **Wo:** `scripts/qa/scan_secrets.py`.
- **Was:** Statische Secret-Erkennung (Cloud-Keys, Private Keys, DB-URLs mit
  Credentials, lange Hex-Tokens, Bootstrap-/Passwort-Zuweisungen). Läuft als
  Gate in der QA-Pipeline. **Aktueller Stand: 0 Befunde** im Repository
  (dokumentierte Test-Platzhalter + Dev-Default-DB-URL + shell-Variablen
  sind gezielt allowlistet).
- **Empfehlung:** Bei Falsch-positiv die Freigabe **in der ALLOWLIST mit
  Begründung** dokumentieren — nie still ignorieren.

## Zusammenfassung

| Severity | Anzahl | IDs |
| --- | --- | --- |
| kritisch | 0 | — |
| hoch | 0 | — |
| mittel | 2 | S1, S3 |
| niedrig | 4 | S2, S4, S5, S9 |
| info | 4 | S6, S7, S8, S10 |

Keine Findung mit aktivem Exploit-Pfad: RBAC-`is_active`-Check (S4) und
parameterisierte Queries (S5) mindern die praktisch relevanten Punkte.
Priorisierte Fixes für R1: **S1** (Audit-FK) und **S3** (Rate-Limit-Key).
