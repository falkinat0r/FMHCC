# R1 — Abnahmecheckliste (Acceptance Checklist)

**Stand:** 2026-11-19 · **Branch:** `deployment/r1-validation` (Basis: `master` = `9bf6afb`)
**Referenz-Playbook:** `docs/deployment/R1-lxc-deployment.md`

Regel: Ein Haken ist nur erlaubt, wenn der Schritt **real ausgeführt** und das
Ergebnis notiert wurde. Nicht Ausgeführtes bleibt offen — niemals
simuliert/angenommen. „n. d.“ = nicht durchgeführt (mit Grund).

---

## A. Vor dem Deployment (Proxmox-Host)

| # | Kriterium | Nachweis (Befehl/Output) | OK |
| --- | --- | --- | --- |
| A1 | Freigabe F1–F5 schriftlich vorliegen (s. Playbook §3) | Betreiber-Notiz: ____________________ | ☐ |
| A2 | Preflight lesend ausgeführt (PVE-Version, CTID frei, Storage, Bridge, RAM, DNS) | Output: ____________________ | ☐ |
| A3 | LXC angelegt: unprivilegiert, 2 vCPU / 3072 MiB / 16 GiB / 512 MiB Swap, `nesting=0` | `pct config <CTID>` (Auszug): ______ | ☐ |
| A4 | Debian-Version im LXC passt zum Template (OS-Release) | `cat /etc/os-release`: ____________________ | ☐ |
| A5 | Tailscale: `/dev/net/tun` durchgereicht und sichtbar im LXC | `ls -l /dev/net/tun`: ____________________ | ☐ |
| A6 | Tailscale verbunden, keine Exit-Node/Subnet-Router-Rolle | `tailscale status`: ____________________ | ☐ |
| A7 | Kein WAN-Zugriff auf den LXC (keine Portweiterleitungen; LAN + Tailscale nur) | Firewall-/Router-Check: ____________________ | ☐ |
| A8 | Backup-Ziel (PVE-Storage) verfügbar, Test-Backup des **leeren** LXC erfolgreich | Backup-ID: ____________________ | ☐ |
| A9 | Git-Checkout des Deployment-Stands vorhanden (sauber, korrekter Commit) | `git -C <checkout> log -1 --oneline`: ______ | ☐ |
| A10 | Node.js ≥ 20.19 im LXC installiert (Frontend-Build) | `node --version`: ____________________ | ☐ |

## B. Deployment (`deploy-lxc.sh --start`)

| # | Kriterium | Nachweis | OK |
| --- | --- | --- | --- |
| B1 | Preflight (Stufe 0) grün, alle Artefakte vorhanden | Log-Auszug: ____________________ | ☐ |
| B2 | Alle 7 Stufen ohne Fehler abgeschlossen | Log: ____________________ | ☐ |
| B3 | Release unter `/opt/hcc/releases/<sha>`, `current`-Symlink korrekt | `readlink /opt/hcc/current`: __________ | ☐ |
| B4 | Backend-Venv aus `uv.lock` (`uv sync --frozen`) gebaut | `ls /opt/hcc/current/backend/.venv/bin/uvicorn` | ☐ |
| B5 | Frontend-Build vorhanden (`frontend/dist/index.html`) | `ls /opt/hcc/current/frontend/dist/` | ☐ |
| B6 | `hcc.env` erzeugt: **keine** Inline-Kommentare, `HCC_ENVIRONMENT=production`, `HCC_COOKIE_SECURE=true`, `HCC_CORS_ORIGINS=[]`, `HCC_GIT_COMMIT=<sha>` (Fix V-1/V-2) | `grep -E '^(HCC_ENVIRONMENT\|HCC_COOKIE_SECURE\|HCC_CORS_ORIGINS\|HCC_GIT_COMMIT)=' /etc/hcc/hcc.env` + `grep '#' /etc/hcc/hcc.env` (muss leer sein) | ☐ |
| B7 | Datei-Rechte: `hcc.env` 0640 root:hcc, `.pg_password` 0600 root | `stat -c '%a %U:%G %n' /etc/hcc/hcc.env /etc/hcc/.pg_password` | ☐ |
| B8 | PostgreSQL: Rolle `hcc` (kein Superuser) + DB `hcc` | `su - postgres -c "psql -c '\du hcc'"` (Auszug) | ☐ |
| B9 | `nginx -t` grün, nginx aktiv | `nginx -t && systemctl is-active nginx` | ☐ |
| B10 | `hcc-api.service` aktiv, Health-Probe (ExecStartPost) bestanden | `systemctl status hcc-api.service --lines=5` | ☐ |
| B11 | Alembic-Migration lief als ExecStartPre ohne Fehler (Version = head) | `journalctl -u hcc-api | grep alembic` (Auszug) | ☐ |
| B12 | Admin-Bootstrap einmalig erfolgreich (201) | Response: ____________________ | ☐ |

## C. Abnahme (Produktionspfad)

| # | Kriterium | Nachweis | OK |
| --- | --- | --- | --- |
| C1 | `GET /api/v1/health/live` → 200 `{"status":"ok"}` (via nginx 127.0.0.1:8080) | Response: ____________________ | ☐ |
| C2 | `GET /api/v1/health/ready` → 200, DB-Check `ok` | Response: ____________________ | ☐ |
| C3 | `GET /api/v1/version` → `commit` == deployed Commit (Feldname `commit`, **nicht** `git_commit` — Fix V-3) | Response: ____________________ | ☐ |
| C4 | `GET /api/v1/openapi.json` erreichbar (`openapi: 3.1.0`) | Response (Auszug): ____________________ | ☐ |
| C5 | E2E-Smoke 8/8 + Aufräum: `sudo bash tests/e2e/e2e-smoke.sh` → Exit 0 | Output: ____________________ | ☐ |
| C6 | — Smoke-Schritt 2 (Version) bestanden mit echten Commit-Wert (V-3-Fix live) | Log-Zeile: ____________________ | ☐ |
| C7 | — Smoke-Schritt 5 (RBAC: Viewer-POST → 403) bestanden, CSRF-Extraktion funktional (V-4-Fix live) | Log-Zeilen: ____________________ | ☐ |
| C8 | — Smoke-Schritt 6 (CSRF: POST ohne Token → 403) bestanden | Log-Zeile: ____________________ | ☐ |
| C9 | Test-Viewer `qa_smoke_viewer` deaktiviert (`is_active=false`), kein aktives Test-Account | `GET /api/v1/users?q=qa_smoke_viewer` (als Admin) | ☐ |
| C10 | Login setzt `hcc_session` (HttpOnly, SameSite=lax) + `hcc_csrf` (SameSite=lax) | Header-Auszug: ____________________ | ☐ |
| C11 | Cookies `Secure` (HTTPS-Pfad via Tailscale Serve) | `set-cookie` zeigt `Secure`: ☐ |
| C12 | 404 liefert Error-Envelope `{error:{code,message,request_id}}` | Response: ____________________ | ☐ |
| C13 | RBAC-Matrix: Viewer kann `POST /users` und `GET /audit` nicht (403) | Status-Codes: ____________________ | ☐ |
| C14 | Deaktivierter User (alte Session) erhält 401 auf geschützten Endpunkten | Status-Code: ____________________ | ☐ |
| C15 | SPA über Tailscale-Serve/TLS erreichbar (Admin-Device) | Adresse: ____________________ | ☐ |
| C16 | Keine öffentliche Erreichbarkeit (WAN-Scan/Negative-Test) | Ergebnis: ____________________ | ☐ |

## D. Daten, Backup, Rollback

| # | Kriterium | Nachweis | OK |
| --- | --- | --- | --- |
| D1 | Erstes CT-Backup **nach** produktivem Setup angelegt | Backup-ID: ____________________ | ☐ |
| D2 | Erstes `pg_dump` (konsistent, außerhalb des Rootfs) angelegt | Datei/Größe: ____________________ | ☐ |
| D3 | Restore-Test: pg_dump in Test-DB geladen, CT-Backup prüffähig | Ergebnis: ____________________ | ☐ |
| D4 | Secrets getrennt/verschlüsselt gesichert (`hcc.env`, `.pg_password`) | Ort/Sicherung: ____________________ | ☐ |
| D5 | `deploy-lxc.sh --list` zeigt die Releases, aktive markiert | Output: ____________________ | ☐ |
| D6 | Rollback-Doku eingesehen, Rollback-Trigger und -Pfad bekannt (s. `R1-rollback.md`) | Betreiber-Notiz: ____________________ | ☐ |
| D7 | Rollback-Übung (optional, empfohlen vor Produktiv-Freigabe): ältestes zweites Release deployen + `--rollback` auf aktives | Output: ____________________ | ☐ |

## E. Sicherheits-Review (R1-Validation)

| # | Kriterium | Nachweis | OK |
| --- | --- | --- | --- |
| E1 | Security-Review abgeschlossen: S1/S3 als **nicht release-blockierend** bewertet, R2-Kandidaten dokumentiert | `docs/deployment/R1-security-review.md` | ☐ |
| E2 | Deploy-Invarianten-Gate (Gate 12) auf dem Deployment-Stand grün | `python scripts/qa/check_deploy_artifacts.py`: ______ | ☐ |
| E3 | Secret-Scan auf dem Deployment-Stand: 0 Befunde | `python scripts/qa/scan_secrets.py`: ______ | ☐ |
| E4 | OpenAPI-Drift-Check grün (Contract unverändert) | `python scripts/qa/check_openapi_drift.py`: ______ | ☐ |
| E5 | Keine neuen Schreibberechtigungen auf Proxmox/Infrastruktur (nur lesend + freigegebener LXC-Pool) | Berechtigungs-Check: ____________________ | ☐ |
| E6 | Kein Docker-Socket, keine offene Shell-API, keine WAN-Ports (s. Playbook §1/§15) | Check: ____________________ | ☐ |

## F. Freigabe

| Rolle | Name | Datum | Unterschrift/Bestätigung |
| --- | --- | --- | --- |
| Betreiber (Freigabe F1–F5) | | | |
| Deployment-Ausführung | | | |
| Abnahme (C1–C16) | | | |
| Sicherheits-Review | | | |

**Gesamtergebnis:** ☐ freigegeben ☐ bedingt freigegeben (offene Punkte: ______)
☐ nicht freigegeben (Begründung: ______)

---

## Evidenzbasis aus der R1-Validation (2026-11-19)

In dieser Validierungsumgebung (Windows, kein Linux/Proxmox/PostgreSQL) wurden
die **Semantiken** der Abnahmeschritte gegen eine lokale R1-Dev-Instanz
(SQLite) real geprüft — als Ersatz-Evidenz, **nicht** als Ziel-LXC-Nachweis:

| Abnahmekriterium | Validiert (Dev-Instanz) | Ziel-LXC |
| --- | --- | --- |
| C1/C2 Health | ✅ 200 + DB-Check ok | n. d. |
| C3 Version (Feld `commit`) | ✅ `{"commit":"validation-test"}` — Beweis für Fix V-3 | n. d. |
| C4 OpenAPI | ✅ `openapi: 3.1.0` | n. d. |
| C5–C9 Smoke-Semantik | ✅ 8 Schritte + Aufräum real ausgeführt (CSRF-Fix V-4: Netscape-Jar belegt, awk-Extraktion liefert Token; ohne Token 403, mit Token 201) | n. d. |
| C10 Cookie-Flags | ✅ `HttpOnly`, `SameSite=lax` (Secure-Flag: production-Check per Settings-Validator, s. C11) | n. d. |
| C12 Error-Envelope | ✅ 404 mit `request_id` | n. d. |
| C13/C14 RBAC + Deaktivierung | ✅ Viewer-POST 403, Viewer-GET /audit 403, Admin-PATCH 200, alte Session 401 | n. d. |
| B6 hcc.env-Generierung | ✅ alte Pipeline bricht (V-1/V-2 empirisch), neue Pipeline → `Settings()` startklar | n. d. |
