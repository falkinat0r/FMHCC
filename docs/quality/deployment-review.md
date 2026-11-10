# R1 — Deployment-Review: unprivilegierter Proxmox-LXC (QA, Agent 5)

Stand: 2026-11-10 · Branch `feature/qa`

Ziel-Plattform: **unprivilegierter Debian-LXC** auf Proxmox, systemd, nginx
(Loopback), PostgreSQL (lokal), Tailscale Serve für TLS. **Kein Docker-in-LXC,
kein AI-Modul, keine reale Deployment-Ausführung in R1** (nur statische Prüfung
+ vorbereitetes Smoke-Skript).

## 1. Bestand (R0) und Bewertung

| Artefakt | Bewertung R0 | R1-Status |
| --- | --- | --- |
| `scripts/deploy-lxc.sh` | 7 Stufen, idempotent, root-/Debian-Check, Zufalls-Token | Preflight, `--list`, `--rollback` ergänzt |
| `deploy/systemd/hcc-api.service` | Loopback-Bindung, Alembic pre-Start, Hardening | `ExecStartPost`-Health-Probe + `TimeoutStartSec=180` ergänzt |
| `deploy/nginx/hcc.conf` | nur `listen 127.0.0.1:8080`, Proxy → `127.0.0.1:8000`, Header | unverändert (Invarianten geprüft) |
| `deploy/systemd/health-probe.sh` | — (neu R1) | wartet bis 30 s auf `health/live` 200 |
| `tests/e2e/e2e-smoke.sh` | — (neu R1) | E2E-Smoke für das LXC (8 Schritte + Aufräum) |

## 2. Statische Invarianten (neu, `scripts/qa/check_deploy_artifacts.py`)

Wird als Gate in der QA-Pipeline ausgeführt (Exit 0/1/2). Prüft u. a.:

- **systemd:** `User=hcc`/`Group=hcc`, `ExecStart` bindet **nur**
  `127.0.0.1:8000`, `ExecStartPre` mit `alembic upgrade head`,
  `ExecStartPost` (Health-Probe) vorhanden, `TimeoutStartSec >= 60`,
  `NoNewPrivileges`/`PrivateTmp`/`ProtectSystem=full`/`ProtectHome`,
  `Restart=on-failure`, `EnvironmentFile=/etc/hcc/hcc.env`,
  **kein** Bezug auf Docker-Socket.
- **nginx:** alle `listen`-Adressen Loopback, `proxy_pass` an Upstream
  `127.0.0.1:8000`, `server_tokens off`, Sicherheits-Header
  (X-Content-Type-Options / X-Frame-Options / Referrer-Policy),
  SPA-Root `/opt/hcc/current/frontend/dist`.
- **deploy-lxc.sh:** `set -euo pipefail`, root-/Debian-Check, Preflight,
  `--list`, `--rollback`, **keine** `curl|sh`/`wget|sh`-Muster, idempotente
  User-Anlage, `chmod 640`/`chown root:hcc` für `hcc.env`, `chmod 600` für
  `.pg_password`, Bootstrap-Token per `openssl rand -hex 24` (kein Literal),
  Migration läuft ausschließlich über systemd-`ExecStartPre`.

**Ergebnis (R1, ausgeführt):** alle Invarianten gehalten → Gate grün.

## 3. R1-Verbesserungen im Detail

### 3.1 `deploy/systemd/hcc-api.service`
- `ExecStartPost=/usr/local/lib/hcc/health-probe.sh` — der Start zählt erst
  als erfolgreich, wenn `/api/v1/health/live` HTTP 200 liefert (bis 30 s
  gepollt). Verhindert „gestartet, aber tot" nach Migration/Start.
- `TimeoutStartSec=180` — Alembic + Probe brauchen Spielraum (neue DB,
  viele Migrations).
- `deploy-lxc.sh` installiert die Probe idempotent nach
  `/usr/local/lib/hcc/health-probe.sh` (0755).

### 3.2 `scripts/deploy-lxc.sh`
- **Preflight (Stufe 0):** prüft vor der ersten Systemänderung, dass
  `.env.example`, `deploy/systemd/hcc-api.service`,
  `deploy/systemd/health-probe.sh`, `deploy/nginx/hcc.conf`,
  `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json` im
  Checkout vorhanden sind und es ein Git-Checkout ist. Uncommittete
  Änderungen → Warnung (es wird `git archive HEAD` deployed).
- **`--list`:** zeigt alle Releases unter `/opt/hcc/releases/` und markiert
  die aktive (Symlink `/opt/hcc/current`).
- **`--rollback <sha>:** verifiziert, dass das Ziel-Release existiert,
  setzt den Symlink atomar um, `systemctl restart hcc-api.service` und
  Health-Probe. Gilt nur, wenn das Ziel bereits deployed war.

## 4. E2E-Smoke (`tests/e2e/e2e-smoke.sh`)

Läuft **nur im Ziel-LXC** (nie in CI). Zeitpunkt: nach Merge +
`deploy-lxc.sh --start`. Deckt über den **Produktionspfad** (nginx
`127.0.0.1:8080`): Health (live/ready), Version, OpenAPI, Login +
HttpOnly-Session, RBAC (Viewer → 403), CSRF (ohne Token → 403),
Error-Envelope (404), SPA. Erzeugt einen Test-Viewer, deaktiviert ihn
am Ende (`PATCH is_active=false`; es gibt bewusst kein DELETE-Nutzer-API).
Credentials kommen aus `HCC_SMOKE_ADMIN`/`HCC_SMOKE_PASS` (kein Default für
Passwort).

## 5. Offene Risiken / bekannte Limitierungen (R1)

| # | Risiko | Bemerkung |
| --- | --- | --- |
| D1 | Deploy-Script **nie unter Linux ausgeführt** (nur statisch + Syntax) | E2E-Smoke ist der Nachweis für die reale Umgebung; R1 darf nicht deployen |
| D2 | `/api/v1/openapi.json` bleibt in Produktion öffentlich | Bewusst (Doku-Vertrag); Sensitivität: nur Schema, keine Daten |
| D3 | Bootstrap-Token bleibt nach Nutzung in `/etc/hcc/hcc.env` | R1-Doku + Smoke weisen darauf hin; Rotation ist ein Betriebsschritt (kein R1-Code) |
| D4 | `.pg_password` (0600 root) dupliziert das Passwort zusätzlich in `hcc.env` (0640 root:hcc) | Akzeptabel (beide nur root/Service); alternative Secret-Verwaltung als R2-Kandidat |
| D5 | Node.js-Installation im LXC bewusst manuell (kein apt-Pin) | Versions-Kopplung an `frontend/package.json` + Lockfile; dokumentiert |
| D6 | Rate-Limiting in-memory (siehe Security S3) | Bei mehreren Instanzen/Last trennt in-memory-Limit nicht sauber |

## 6. Empfehlung

- Nach Merge: im LXC `deploy-lxc.sh --start`, dann `tests/e2e/e2e-smoke.sh`
  ausführen → erst danach als „produktiv" betrachten.
- Rollback-Pfad (`--rollback`) in die Betriebs-Doku aufnehmen.
- `openapi.json`-Publikation (D2) bei Bedarf hinter Auth stellen —
  wäre Contract-/Konfig-Änderung, über R1-Vorschlags-Prozess.
