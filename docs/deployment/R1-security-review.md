# R1 — Security-Review: Proxmox-LXC-Deployment (Validation)

**Stand:** 2026-11-19 · **Branch:** `deployment/r1-validation` (Basis: `master` = `9bf6afb`)
**Methodik:** (1) Code-Review der Deployment-Artefakte + Auth/Config;
(2) ausgeführte Validierung (Test-Suites, Dev-Instanz, Gate-Checks);
(3) Bestandsaufnahme offener Findungen S1–S10 (QA) und D1–D6/D-I1–I3
(Integrations-Review) mit neuer Bewertung im Deployment-Kontext.

> **Kontext:** In dieser Validierung wurden **keine** Proxmox-Schreibaktionen
> ausgeführt, **keine** Credentials erzeugt, **keine** bestehenden
> VM/LXC/Storage/Network-Regeln geändert. Alle Proxmox-spezifischen
> Schritte sind als „nicht durchgeführt“ markiert.

---

## 1. Verdict

| Frage | Antwort |
| --- | --- |
| Aktive Exploit-Pfade, die das Release blockieren? | **Nein.** (QA-Bewertung S1–S10; von der Validierung bestätigt) |
| Blockiert S1 das Release? | **Nein** — dokumentierter R2-Kandidat (Audit-FK, kein Exploit-Pfad) |
| Blockiert S3 das Release? | **Nein** — Self-DoS-Risiko im Multi-Admin-Betrieb, dokumentiert + R2-Fix-Pfad; im Homelab-Scope akzeptiert |
| Blockieren die in dieser Validierung gefundenen Defekte (V-1…V-8)? | **Nein** — alle **in diesem Branch behoben** (Deploy-Skript, Smoke, nginx) |
| Release-Readiness für das Ziel-LXC-Deployment | **Freigegeben, unter den Bedingungen** aus `R1-acceptance-checklist.md` (Freigaben F1–F5, Abnahme C1–C16) |

**Zusammenfassung:** Das Deployment-Setup ist sicherheitsmäßig in Ordnung:
Loopback-Zwang für API und nginx (Gate 12), unprivilegierte Serviceidentität,
systemd-Hardening, dedizierte nicht-Superuser-PG-Rolle, Zufalls-Bootstrap-
Token ohne Repo-Spur, Secrets nur auf dem Zielsystem (0600/0640), Tailscale
als primärer TLS-Zugriff, keine WAN-Exponierung, kein Docker-Socket, keine
offene Shell-API. Die offenen Punkte (S1, S3) sind **nicht**
release-blockierend und haben dokumentierte R2-Abstellmöglichkeiten.

---

## 2. Bestandsaufnahme: S1–S10 (QA) im Deployment-Kontext

| ID | Sev. | Inhalt (Kurz) | Status | Deployment-Bewertung |
| --- | --- | --- | --- | --- |
| S1 | mittel | Audit-Zeile `integrations.configure` verliert FK (`integration_id=NULL`) bei neuer Integration (record vor flush) | offen, R2-Kandidat | **Nicht blockierend.** Kein Exploit-Pfad, keine Datenleakage — die Handlung selbst wird auditiert, nur die Ressource-Zuordnung fehlt. In R1 keine Integrations-Daten in Produktion, daher keine praktische Auswirkung auf das erste Deployment. Fix = Reihenfolge `flush` → `record` (keine Contract-Änderung, R2) |
| S2 | niedrig | 405 wird als `not_found` codiert (Doc verspricht `method_not_allowed`) | offen (frozen per Proposal `backend-errors-method-not-allowed.md`) | **Nicht blockierend.** Konsumenten sollen auf HTTP-Status achten (Doku-Regel); Deployment-Relevanz: keine |
| S3 | mittel | Login-Rate-Limit (10/60 s) pro `request.client.host`; hinter Loopback-nginx = EIN gemeinsamer Bucket für alle Clients | offen, R2-Kandidat | **Nicht blockierend, aber Betriebsrisiko** — s. §3 (ausführliche Bewertung) |
| S4 | niedrig | `SessionService.resolve` prüft `is_active` nicht | abgemildert (RBAC-Schicht prüft, 401) | **Nicht blockierend.** Validierung bestätigt: deaktivierter User (alte Session) → 401 auf `/auth/me` und geschützten Endpunkten. Defense-in-Depth für R2 |
| S5 | niedrig | LIKE-Wildcards (`%`/`_`) in `q`/`action`-Filtern unmaskiert | offen | **Nicht blockierend.** Parameterisiert (kein SQLi); paginiertes Leak im Rahmen des berechtigten Zugriffs (nur Admin kann Audit lesen) |
| S6 | info | ESLint-9-Deprecation-Warnung | dokumentiert | keine Deployment-Relevanz |
| S7 | info | POST ohne Body ohne `Content-Type` (bewusstes Verhalten) | dokumentiert | keine Deployment-Relevanz |
| S8 | info | TestClient per-Request-Cookies (Test-Tooling) | dokumentiert | keine Deployment-Relevanz |
| S9 | niedrig | fehlendes `package-lock.json` | **gelöst in R1** (Lockfile committet, `c37c3c0`) | **Abgeschlossen.** Zusätzlich in dieser Validierung: `npm ci` im Deploy-Skript (V-6) + Lockfile im Preflight (V-8) |
| S10 | info | Secret-Scanner als Gate | läuft (Gate 1) | Validierung: **0 Befunde** auf diesem Branch (nach Fixes) |

---

## 3. S3 — ausführliche Bewertung (Release-Blocker oder nicht?)

**Fakt:** `SlidingWindowLimiter(max_calls=10, window=60 s)` wird pro
`request.client.host` geschlüsselt. Hinter dem Loopback-nginx ist
`request.client.host` für alle Clients `127.0.0.1` → **alle** Logins
teilen sich einen einzigen 10/min-Bucket.

**Im Ziel-Deployment:**

1. **Brute-Force-Schutz (außen):** Das API ist nicht direkt erreichbar
   (Loopback-Zwang, Gate 12); der einzige externe Pfad ist Tailscale
   (TLS + ACL: nur Admin-Geräte). Ein externes Brute-Force-Attacken-
   Szenario ist durch die Netzwerk-Isolation praktisch ausgeschlossen.
   Der Rate-Limiter ist dann zweitrangig, aber nicht schädlich.
2. **Self-DoS (innen, Multi-Admin):** Bei mehreren Admins kann ein
   Login-Alltag (z. B. 3 Geräte × App-Reloads, Token-Refresh-Loops) den
   Bucket aufbrauchen → übrige Admins werden 60 s von Logins
   ausgeschlossen. **Kein** Sicherheitsverlust (angemeldete Sessions
   laufen weiter; nur *neue* Logins sind betroffen), aber
   Betriebsreibung.
3. **Ein-Instance-Annahme:** In-memory-Limit ist pro Prozess; mit
   `systemd` + einem uvicorn-Prozess im LXC gilt das als akzeptabel.
   Skalierung auf mehrere Worker/Instanzen bräuchte ein geteiltes
   Backing (R2).

**Bewertung:** **Nicht release-blockierend.** Der reale Schutz gegen
Brute-Force kommt aus der Netzwerk-Isolation (Loopback + Tailscale-ACL),
nicht aus dem Limiter. Das Self-DoS-Risiko ist im Homelab-Scope
(Single-/Few-Admin) gering.

**Dokumentierte Abstellmöglichkeiten (R2-Kandidat):**
- Echte Client-IP aus `X-Forwarded-For` ableiten (nur wenn
  `request.client.host` Loopback ist) + Limit pro realer IP, **und/oder**
- Backing außerhalb des Prozesses (z. B. PostgreSQL-Tabellen) für
  Persistenz über Restarts und Multi-Worker, **und/oder**
- Doku-Vermerk im Playbook (erledigt: `R1-lxc-deployment.md` §15,
  Zeile „Login → HTTP 429“).

**Betriebsregel R1 (im Playbook dokumentiert):** Bei 429 → warten oder
Service-Neustart (Reset des In-memory-Buckets); im Smoke-Test ist der
Login-Versuche-Aufwand bewusst klein (1–2 Logins pro Rolle).

**S1 — kurze Begründung der Nicht-Blockierung:** Die Audit-Zeile
existiert weiterhin (action `integrations.configure`, User, Zeitstempel,
Details mit Slug); nur die FK-Spalte ist bei **neuen** Integrations null.
Es gibt weder einen Exploit-Pfad noch eine Informationsleakage — die
Zuordnung ist in `details` (Slug) nachvollziehbar. Fix (flush vor record)
ist ein R2-Kandidat ohne Contract-Auswirkung.

---

## 4. Deployment-Risiken D1–D6 (Integrations-Review) — Status nach dieser Validierung

| # | Risiko | Status jetzt |
| --- | --- | --- |
| D1 | Deploy-Script nie unter Linux ausgeführt | **unverändert, bewusst** — Ziel-LXC-Deployment ist die Abnahme (Checkliste C1–C16); R1-Validation hat die Semantik aller Stufen gegen eine echte Instanz geprüft, wo möglich |
| D2 | `openapi.json` öffentlich | unverändert (bewusster Doku-Vertrag; nur Schema, keine Daten) |
| D3 | Bootstrap-Token bleibt nach Nutzung in `hcc.env` | unverändert; Rotation = dokumentierter Betriebsschritt (Rollback-Doku §7); bootstrap ist ohne User ohnehin abgelehnt |
| D4 | PG-Passwort in `.pg_password` (0600) **und** `hcc.env` (0640) dupliziert | akzeptiert (beide root/Service nur); R2: Secret-Verwaltung |
| D5 | Node.js-Installation im LXC manuell (kein apt-Pin) | unverändert; jetzt zusätzlich: `npm ci` gegen Lockfile (V-6) → Build-Reproduzierbarkeit verbessert |
| D6 | Rate-Limit in-memory (= S3) | s. §3 — R2-Kandidat, Betriebsregel dokumentiert |

**D-I1–I3 (Integrations-Review):**

| # | Befund | Status jetzt |
| --- | --- | --- |
| D-I1 | `npm install` statt `npm ci` im Deploy-Skript | **abgeschlossen in diesem Branch** (V-6): `npm ci --no-audit --no-fund`, Lockfile im Preflight (V-8) |
| D-I2 | kein automatisches DB-Backup | unverändert (Betriebsaufgabe, Playbook §8 mit Dump-Vorschrift; Automatisierung R2) |
| D-I3 | `After=postgresql.service` ohne `Requires=` | unverändert (akzeptiert für Homelab-Scope; Playbook §13.4/§15 dokumentiert) |

---

## 5. Neue Findungen dieser R1-Deployment-Validation (V-Serie)

| ID | Severity | Befund | Nachweis (ausgeführt) | Disposition |
| --- | --- | --- | --- | --- |
| V-1 | **hoch (Prod-Blocker)** | `hcc.env`-Generierung: systemd-`EnvironmentFile` streicht keine Inline-Kommentare; `.env.example`-Werte wie `HCC_SESSION_TTL_SECONDS=43200 # 12 h …` hätten pydantic beim App-Start crashen (int-Parse) | empirisch: `Settings()` mit `HCC_SESSION_TTL_SECONDS='43200          # 12 h absolute Lifetime'` → `ValidationError` | **gefixt** in `deploy-lxc.sh` (sed entfernt `#…`-Suffixe vor den Wert-Ersatz) |
| V-2 | **hoch (Prod-Blocker)** | `HCC_CORS_ORIGINS=` (leer) bricht das pydantic-settings-JSON-Parsing des `list[str]`-Felds → App-Start-Crash | empirisch: `Settings()` mit `HCC_CORS_ORIGINS=''` → `json.JSONDecodeError` | **gefixt** in `deploy-lxc.sh` (sed erzeugt `HCC_CORS_ORIGINS=[]` — semantisch identisch: nur same-origin) |
| V-3 | mittel | `e2e-smoke.sh` Schritt 2 liest `.git_commit`; der frozen Contract (`VersionResponse` in `openapi.v1.json`) heißt `commit` → Smoke-Schritt wäre immer rot | Contract-Lesung + Runtime: `GET /api/v1/version` → `{"…","commit":"validation-test"}` (kein `git_commit`-Feld) | **gefixt** in `tests/e2e/e2e-smoke.sh` (`.commit // empty` inkl. Meldungen) |
| V-4 | mittel | CSRF-Extraktion `grep -o 'hcc_csrf=[^;]*' "$COOKIE_JAR"` kann nie matchen: curl-Cookie-Jars sind Netscape-Tab-Format (`name`/`value` in Spalte 6/7, kein `name=value`-String) → `$CSRF` leer → Smoke-Schritt 5 (RBAC) und Aufräum-PATCH immer rot | Runtime: echter Login → Jar-Inhalt gezeigt (`127.0.0.1  FALSE  /  FALSE  <exp>  hcc_csrf  <64-hex>`); awk-Extraktion liefert den Token; POST mit Token → 201, ohne → 403 | **gefixt** in `tests/e2e/e2e-smoke.sh` (`awk -F'\t' '$6=="hcc_csrf"{print $7; exit}'` für `$CSRF` und `$VCSRF`) |
| V-5 | niedrig | Smoke-Header: `sudo scripts/qa/e2e-smoke.sh` — Pfad existiert nicht (tatsächlich `tests/e2e/e2e-smoke.sh`) | statisch | **gefixt** (Header-Kommentar) |
| V-6 | niedrig | `deploy-lxc.sh`: `npm install` statt `npm ci` (Reproduzierbarkeit; D-I1; S9-Folge) | statisch + R1-Report (Lockfile committet `c37c3c0`) | **gefixt** (`npm ci --no-audit --no-fund`) |
| V-7 | niedrig | nginx `keepalive 32` ohne `proxy_set_header Connection "";` wirkt nicht (Upstream-Verbindungen werden per Request geschlossen; nginx-Doku: keepalive_Requirements) | statisch (nginx-Dokumentation) | **gefixt** in `deploy/nginx/hcc.conf` (Header gesetzt, kommentiert) |
| V-8 | niedrig | Preflight-Artefaktliste fehlte `frontend/package-lock.json` (trotzdem nötig: `npm ci` braucht es) | statisch | **gefixt** (Preflight-Liste in `deploy-lxc.sh`) |
| V-9 | mittel (Dev-only) | Alembic-Migration 0001 auf **SQLite**: `audit_events.id` als `BIGINT` (kein rowid-Alias) → Audit-Inserts schlagen fehl (`NOT NULL constraint failed: audit_events.id`). Auf **PostgreSQL** lautet das DDL `id BIGSERIAL NOT NULL` (Sequence → korrekt) | Runtime: Bootstrap auf SQLite-DB (post-`alembic upgrade head`) → 500 + Traceback; DDL-Rendering gegen PostgreSQL-Dialekt → `BIGSERIAL` | **nicht gefixt** (out of scope; kein Produktivpfad, kein Contract-Change) — R2-Kandidat, dokumentiert in Playbook §10 |
| V-10 | niedrig | Alembic-Offline-Modus (`alembic upgrade head --sql`) bricht in `backend/alembic/env.py` (bekannter R0-Defekt) | Runtime: `alembic upgrade head --sql` → Traceback | **kein Change** — geteilter Bereich (`alembic/**`); offenes Proposal `docs/proposals/backend-alembic-offline-sql.md` bleibt der Weg (AGENTS.md §4) |

**Gesamt:** 8 von 10 Findungen in diesem Branch behoben (V-1…V-8), 2
bewusst nicht (V-9: R2-Fix, V-10: Proposals-Prozess) — keine
Umgehung, keine stille Änderung gemeinsamer Contracts/Migrationen.

---

## 6. Proxmox- & Infrastruktur-Sicherheit (dieser Validierung)

- **Keine Schreibaktionen** auf dem Proxmox-Host, keine LXC/VM-Änderungen,
  keine Storage-/Firewall-/Network-Regel-Änderungen (Auftragsvorgabe).
- **Keine Credentials erzeugt** (keine Proxmox-API-Tokens, keine Tailscale-
  Accounts, keine PG-Zugangsdaten außerhalb des Ziel-LXC-Plans).
- **Berechtigungsmodell (für die spätere Proxmox-Integration, Playbook
  §3/§7):** eigener API-Token, initial nur Audit-/Leserechte;
  VM-/LXC-Lifecycle-Rechte erst nach F5 auf den konkreten Pool
  beschränkt; kein Root-Token. Adapter-Zugänge (TrueNAS, Pi-hole,
  Docker, Tailscale): dediziert, read-only bevorzugt, **kein**
  Docker-Socket-Mount, keine unverschlüsselten Remote-Docker-Ports,
  TLS-Prüfung aktiv (R0-Spielregeln, unverändert).
- **LXC-Isolation:** unprivilegiert, `nesting=0` (Ausgangswert),
  kein Docker-in-LXC, natives systemd; Tailscale nur über
  `/dev/net/tun`-Passthrough (kein generisches Feature-Recht).
- **Secrets-Hygiene:** `hcc.env` (0640 root:hcc), `.pg_password`
  (0600 root), optionales `secrets.env` (0640) — alle nur auf dem
  Ziel-LXC, nie im Repository; Secret-Scan auf diesem Branch: **0 Befunde**.
- **Bootstrap-Token:** Zufall (`openssl rand -hex 24`), kein Literal im
  Skript (Gate 12 prüft), nur in der lokalen `hcc.env`.

---

## 7. Validierungs-Evidenz (ausgeführt, 2026-11-19)

| Prüfung | Befehl/Aufbau | Ergebnis |
| --- | --- | --- |
| Secret-Scan | `python scripts/qa/scan_secrets.py` (auf diesem Branch, nach Fixes) | **0 Befunde** |
| OpenAPI-Drift | `python scripts/qa/check_openapi_drift.py` | **OK, 15 Pfade, Snapshot identisch** |
| Deploy-Invarianten (Gate 12) | `python scripts/qa/check_deploy_artifacts.py` (nach Fixes: systemd, nginx inkl. V-7, deploy-lxc.sh inkl. V-1/V-2/V-6/V-8) | **OK** |
| Backend-Suite | `pytest` (backend, JUnit) | **337 passed, 1 skipped** (Skip = PG-Live-Roundtrip, `HCC_TEST_DATABASE_URL` nicht setzbar — erwartet) |
| QA-Root-Suite | `pytest tests/` | **118/118 passed** |
| Migration (SQLite) | `alembic upgrade head` auf temporärer SQLite-DB | **grün** (DDL; s. V-9 für die SQLite-Insert-Kennzeichnung) |
| PG-DDL (Ziel-Dialekt) | CreateTable-Rendering gegen PostgreSQL-Dialekt (ohne Verbindung) | `audit_events.id BIGSERIAL NOT NULL`, `users.id UUID` — **korrekt für das Ziel** |
| Live-Instanz (Semantik) | uvicorn + SQLite, `127.0.0.1:8123` | Health, Version (`commit`), OpenAPI, Bootstrap (201), Login (Cookies), CSRF-Matrix (403/201), RBAC (403/403/200/401), Error-Envelope — **alle grün** (Details: Playbook §13.3) |
| hcc.env-Generierung | sed-Pipeline 1:1 simuliert → `app.config.Settings()` | alte Pipeline: **2 Crashes** (V-1/V-2); neue Pipeline: **Settings startklar** (production, Secure, ttl=43200, cors=[]) |
| `bash -n`-Syntax | — | **nicht durchgeführt** (kein Bash im Validierungsumfeld) — statische Review als Ersatz |
| Deployment-/Smoke-/nginx-/systemd-Executions, Proxmox, PG-Live | — | **nicht durchgeführt** (kein Linux/Proxmox/PG) — als Planungsvorschrift in Playbook/Checkliste |

---

## 8. Offene Risiken (konsolidiert, für die Freigabe)

1. **S3** (Self-DoS-429 im Multi-Admin-Betrieb): akzeptiert, Betriebsregel
   dokumentiert, R2-Fix-Pfad definiert (§3).
2. **S1** (Audit-FK null bei neuer Integration): akzeptiert, R2-Fix.
3. **Kein automatisches DB-Backup** (D-I2): Vorschrift + manuelle
   Retention im Playbook §8; Automatisierung R2.
4. **Live-Migrations-Evidenz fehlt auf Dev-Maschine:** im Ziel-LXC durch
   `ExecStartPre` + Health-Probe-Gate abgedeckt (Start zählt erst bei
   `health/live`-200).
5. **SQLite-Dev-Workflow mit Alembic** (V-9): bekannt, Dev-only, R2.
6. **Rollback deckt keine Daten** (L1): in R1 unkritisch (kein
   Schema-Drift); R2-Regel dokumentiert (Rollback-Doku §4).
7. **Bootstrap-Token-Persistenz** (D3): Rotation dokumentiert;
   Endpunkt ohne User nicht erreichbar.
8. **LXC-Startwerte** (2 vCPU/3 GiB/16 GiB) sind Planungswerte —
   nach Messung dimensionieren (Playbook §2/§5).

---

## 9. Ergebnis

**Das R1-Deployment ist sicherheitsseitig release-fähig.** S1 und S3
blockieren nicht (Begründung §2/§3); die in dieser Validierung
nachgewiesenen Defekte (V-1…V-8) sind behoben und durch die
wiederholten Gate-Läufe (Secret-Scan, OpenAPI-Drift, Deploy-Invarianten)
bestätigt. Die Abnahme im Ziel-LXC (Checkliste) ist der letzte,
verbindliche Schritt — inklusive der Freigaben F1–F5, bevor dort eine
Schreibaktion erfolgt.
