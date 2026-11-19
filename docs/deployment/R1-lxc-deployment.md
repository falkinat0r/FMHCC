# R1 — Proxmox-LXC-Deployment-Playbook

**Stand:** 2026-11-19 · **Branch:** `deployment/r1-validation` (Basis: `master` = `9bf6afb`)
**Ziel:** HCC R1 auf einem unprivilegierten Debian-LXC (Proxmox VE) betriebsfertig
deployen — ausgehend von der Windows-Admin-Workstation.

> **Validierungsstatus dieser Doku (ehrliche Kennzeichnung):**
> Alle in der Validierungsumgebung (Windows, kein Linux, kein Proxmox-Zugriff,
> kein PostgreSQL) tatsächlich ausführbaren Schritte wurden **real ausgeführt**
> und sind mit Evidenz belegt (Abschnitt 13, §13.3). Alle Linux-, Proxmox- und
> PostgreSQL-spezifischen Schritte sind als **„nicht durchgeführt"** markiert —
> sie sind überprüfbare Planungsvorschriften, keine simulierten Ergebnisse.
> `bash -n`-Syntaxprüfung: nicht durchführbar (kein Bash) — durch statische
> Code-Review ersetzt.

Gliederung: 15 Pflicht-Abschnitte, wie im Deployment-Auftrag vorgegeben.

---

## 1. Ziel, Geltungsbereich, Abgrenzung

**Ziel:** Reproduzierbares, idempotentes Deployment von HCC R1 (Backend +
Frontend + PostgreSQL + systemd + nginx) in einen unprivilegierten Debian-LXC
auf Proxmox VE, inklusive Abnahme- und Rollback-Vorschrift.

**Geltungsbereich (IN Scope):**
- LXC-Anlage (unprivilegiert), Tailscale-Vorbereitung, Netzwerk,
- Deployment über `scripts/deploy-lxc.sh` (Stufen 0–7),
- PostgreSQL-Setup (lokale Instanz, dedizierte Rolle),
- systemd-Unit `hcc-api.service` (eingefrorenes Deployment-Vertrag),
- nginx-Site (Loopback-only) inkl. Keepalive-Fix (R1-Validation, V-7),
- Ersteinrichtung (einmaliger Admin-Bootstrap),
- Abnahme (E2E-Smoke `tests/e2e/e2e-smoke.sh`), Healthchecks, Rollback.

**Abgrenzung (OUT of Scope):**
- **Keine** produktiven Änderungen an bestehender Infrastruktur ohne
  explizite Freigabe (Abschnitt 3); dieses Playbook selbst erzeugt keine
  Schreibaktionen.
- Kein Docker-in-LXC, keine Container-Stacks.
- **Keine KI-/LLM-/Agent-Funktionen** (AGENTS.md-Regel 6; HCC ist bewusst
  ohne AI-Modul).
- Kein Monitoring-Stack (Prometheus/Grafana) wird neu installiert — nur
  Anbindung existierender Instanzen, falls vorhanden.
- Keine WAN-Portweiterleitung, keine öffentliche Erreichbarkeit des HCC.
- Proxmox-API-Berechtigungen für die spätere Proxmox-Integration (R2+)
  werden hier nur lesend vorbereitet, nicht vergeben.

**Eingebettete Dokumente:**
- Abnahmekriterien: `docs/deployment/R1-acceptance-checklist.md`
- Rollback: `docs/deployment/R1-rollback.md`
- Sicherheit (S1/S3, D1–D6, V-1–V-10): `docs/deployment/R1-security-review.md`

---

## 2. Zielumgebung und technische Annahmen

| Parameter | Wert | Status |
| --- | --- | --- |
| Proxmox-Host | i7-4790, 32 GB RAM (Annahme aus R0-Playbook) | **nicht verifiziert** (kein Host-Zugriff in dieser Validierung) |
| LXC-Typ | **unprivilegiert** (User-Namespaces), kein Privileged | Planwert |
| Gast-OS | Debian (Template-Version der PVE-Version passend; `pveam` prüfen) | Planwert |
| vCPU / RAM / Rootfs | 2 / 3072 MiB / 16 GiB (+ 512 MiB Swap) | **Startwerte** — nach Messung anpassen (R0-Playbook §11) |
| Lokale DB | PostgreSQL (Debian-Paket), dedizierte Rolle `hcc` (kein Superuser) | im LXC |
| Erreichbarkeit | LAN + Tailscale (MagicDNS), **keine** WAN-Exponierung | Planwert |
| TLS | Tailscale Serve vor nginx `127.0.0.1:8080` (bzw. dokumentierter interner HTTPS-Proxy) | Planwert |
| Service-Laufzeit | natives systemd; `hcc-api.service` (User `hcc`), `nginx` | im LXC |
| Frontend-Build | Node.js ≥ 20.19 (`frontend/package.json` engines), `npm ci` gegen Lockfile | manuell im LXC |

**Vertraute Layout-Konventionen** (im Skript implementiert, Gate 12 geprüft):

```
/opt/hcc/releases/<commit-sha>/{backend,frontend}   # ein Release pro Commit
/opt/hcc/current -> releases/<commit>               # atomares Symlink
/opt/hcc/tools/uv/                                   # uv (via pip, kein curl|sh)
/etc/hcc/hcc.env        (0640 root:hcc)              # niemals im Repository
/etc/hcc/.pg_password   (0600 root)
/etc/hcc/secrets.env    (0640, optional; Adapter-Secrets)
/var/lib/hcc  /var/log/hcc
/usr/local/lib/hcc/health-probe.sh (0755)
```

**Bind-Zwang (vertraglich, Gate 12):** Backend bindet ausschließlich
`127.0.0.1:8000`; nginx ausschließlich `127.0.0.1:8080`. Jeder Nicht-Loopback-
Listenport bricht das Deploy-Invarianten-Gate.

---

## 3. Freigaben und Vorbedingungen (Gate vor jeder Schreibaktion)

**Kein Schritt in Abschnitt 4+ darf Schreibzugriff erzeugen, bevor alle fünf
Punkte schriftlich durch den Betreiber bestätigt sind.** In dieser
Validierung wurden **keine** Proxmox-Schreibaktionen ausgeführt und **keine**
Credentials erzeugt — der Punkt ist hier bewusst eine Hürde, keine Formalie.

| # | Vorbedingung | Bestätigt durch |
| --- | --- | --- |
| F1 | Zielhost eindeutig benannt (Name/IP), PVE-Version bekannt | Betreiber |
| F2 | LXC-ID (CTID) gewählt und frei (via `pct list`) | Betreiber |
| F3 | Netzwerk-Parameter fest (Bridge, IP-Schema: DHCP oder statisch, DNS) | Betreiber |
| F4 | Backup-Ziel vorhanden und **einmal testweise** nutzbar (PVE-Backup-Storage) | Betreiber |
| F5 | Explizite, dokumentierte Freigabe für LXC-Anlage + Deployment auf diesem Host | Betreiber |

Zusätzliche harte Bedingungen:
- Kein Privileged-Container, keine AppArmor-Abschaltung, keine
  `nesting=1`/`keyctl`-Features ohne begründete Notwendigkeit.
- Kein ungeprüftes remote `curl \| sh` auf dem Host (R1-Regel, Gate 12).
- Proxmox-Zugriff: eigener API-Token mit **minimalen Rechten** — für dieses
  Playbook: initial **nur Audit-/Leserechte**; Schreibrechte (LXC-Lifecycle)
  erst ab F5 auf den konkreten CTID-Pool beschränkt. Kein Root-Token.
- Alle Platzhalter (`CTID`, `STORAGE`, `VM_BRIDGE`, `DEBIAN_TEMPLATE`) sind
  **Beispielwerte** aus dem R0-Playbook und vor jeder Ausführung zu ersetzen.

---

## 4. Preflight auf dem Proxmox-Host (nur lesend)

**Status: nicht durchgeführt** (kein Host-Zugriff in dieser Validierung).
Befehle sind lesend und dürfen ohne F5 ausgeführt werden, sobald F1–F4 vorliegen:

```bash
pveversion -v
pct list                              # freie CTID, vorhandene CTs
pvesm status                          # Backup-/Template-Storage
ip -br addr                           # Bridges, Adressierung
free -h                               # freie RAM
pveam available --section system | grep -E 'debian-13|debian-12' | head
```

**Prüfliste:** freie CTID · Template vorhanden (Version passend) ·
Backup-Storage mit freiem Platz · Bridge für `net0` · DNS auflösbar
(`getent hosts deb.debian.org`) · IPv4-Vergabe (DHCP/Statik) · PVE-Firewall-
Regeln für den LXC-Bereich nicht restriktiver als benötigt.

---

## 5. LXC anlegen (unprivilegiert) — erst nach F5

**Status: nicht durchgeführt.** Beispiel mit expliziten Platzhaltern:

```bash
# Auf dem Proxmox-Host. WERTERSETZEN vor Ausführung:
CTID=240
STORAGE=local-lvm
VM_BRIDGE=vmbr0
DEBIAN_TEMPLATE='local:vztmpl/<exact-debian-template>.tar.zst'

pct create "$CTID" "$DEBIAN_TEMPLATE" \
  --hostname hcc \
  --unprivileged 1 \
  --cores 2 --memory 3072 --swap 512 \
  --rootfs "$STORAGE:16" \
  --net0 "name=eth0,bridge=$VM_BRIDGE,ip=dhcp" \
  --onboot 1 \
  --features nesting=0

pct start "$CTID"
pct exec "$CTID" -- bash -lc 'cat /etc/os-release; ip -br addr; getent hosts deb.debian.org'
```

**Hinweise:**
- `nesting=0` ist Ausgangswert; vor Produktivbetrieb prüfen, ob einzelne
  systemd-/Isolation-Funktionen im unprivilegierten LXC Einschränkungen zeigen
  (insb. `ProtectSystem`, `PrivateDevices` — s. Abschnitt 15).
- Startwerte 2 vCPU/3 GiB/16 GiB sind **Planungswerte**; nach R1-Messung
  (RSS, CPU, I/O, DB-Größe) dimensionieren. Bei lokalem PG mit hoher
  Event-Retention ggf. 4 GiB/32 GiB.
- SSH im LXC: Standard-Debian (sshd im Template). Kein SSH-Access von WAN;
  SSH-Nutzung über LAN oder Tailscale.

---

## 6. Tailscale-Voraussetzungen im unprivilegierten LXC

**Status: nicht durchgeführt** (keine Ausführung; Voraussetzungen geprüft
gegen die offizielle Tailscale-Dokumentation für unprivilegierte LXC).

Tailscale im unprivilegierten LXC braucht **zwei** Voraussetzungen, die
beide auf Host-Seite kontrolliert werden:

1. **`/dev/net/tun`-Passthrough** (Pflicht): Der WireGuard-Stack braucht das
   TUN-Gerät. Im unprivilegierten LXC nur durch explizite Device-Durchreichung
   verfügbar:

   ```bash
   # Auf dem Proxmox-Host (nach LXC-Anlage, vor tailscale up):
   pct shutdown "$CTID"
   pct set "$CTID" --dev0 /dev/net/tun
   pct start "$CTID"
   pct exec "$CTID" -- ls -l /dev/net/tun    # muss existieren
   ```

   Fehlt die CLI-Option in der eingesetzten PVE-Version: Proxmox UI →
   CT → Resources → Add → **Device Passthrough** → `/dev/net/tun`.
   **Kein** generisches `--features`-Recht wie `keyctl`/`nesting=1`
   nur „weil Tailscale es vielleicht braucht" — nur das konkrete Device.

2. **Kein Exit-Node/Subnet-Router** (Sicherheitsregel): HCC-LXC ist reines
   Member-Device. `tailscale up --accept-routes=false
   --advertise-exit-node=false`. ACL/Grants: nur die persönlichen
   Admin-Geräte dürfen den HCC erreichen.

**Installation im LXC** (nach Prüfung des offiziellen Installationswegs,
Paketsignaturen prüfen — kein ungeprüftes `curl | sh`):

```bash
apt update
apt install -y curl ca-certificates
# [offiziellen Tailscale-Installationsweg ausführen]
tailscale up --accept-routes=false --advertise-exit-node=false
tailscale status
```

**Verifikation (Teil der Abnahme, s. Abschnitt 13):**
- `tailscale status`: verbunden, Stable-IP sichtbar.
- MagicDNS/ACL: HCC erreichbar über Tailscale-Adresse vom Admin-Device.
- Konsistenz Pi-hole/MagicDNS/`resolv.conf` im LXC prüfen, falls vorhanden.
- TLS: Tailscale Serve vor `http://127.0.0.1:8080` (Loopback-nginx) —
  davor testen, welche Adresse/Zertifikatsfunktion real verfügbar ist
  (R0-Playbook §6).

---

## 7. Netzwerk, Erreichbarkeit, TLS

| Pfad | Konfiguration | Bemerkung |
| --- | --- | --- |
| Backend | `127.0.0.1:8000` (uvicorn, systemd) | Loopback-Zwang (Gate 12) |
| nginx | `127.0.0.1:8080` | Loopback-only; SPA + `/api/`-Proxy |
| LAN | HCC-IP des LXC (DHCP/Statik) | HTTP allenfalls im isolierten Testnetz |
| Tailscale | Serve → `127.0.0.1:8080` | **primärer** Zugriff mit TLS |
| WAN/Internet | — | **keine** Portweiterleitung, keine öffentliche Exponierung |

- CORS restriktiv: `HCC_CORS_ORIGINS=[]` (nur same-origin) — wird vom
  Deploy-Script so erzeugt (Fix V-2, s. Abschnitt 9). Bei Bedarf als
  JSON-Liste ergänzen, z. B. `["https://hcc.<tailscale-domain>"]`.
- Cookies in Produktion: `Secure` (Fail-Fast-Validator in `app/config.py`
  erzwingt `HCC_COOKIE_SECURE=true` bei `environment=production`),
  `HttpOnly` für `hcc_session`, `SameSite=Lax` — validiert in der
  Validierung (Abschnitt 13.3, Login-Header-Evidenz).
- `openapi.json` bleibt bewusst öffentlich (D2: nur Schema, keine Daten).

---

## 8. Backup vor dem Deployment (Punkt 0)

**Status: nicht durchgeführt** (kein Host-Zugriff). Vorschrift:

1. **CT-Backup (Ganzes LXC):** Proxmox-Backup (z. B.
   `vzdump "$CTID" --mode snapshot --storage <backup-storage>` oder
   UI → Backup) **vor** dem ersten `deploy-lxc.sh`-Lauf und **vor**
   jedem größeren Update. Ziel: PVE-Backup-Storage (F4).
2. **PostgreSQL-Dump (konsistent):** nach dem Deployment, da die DB noch
   leer/initial ist, und danach regelmäßig:
   ```bash
   # im LXC, als postgres-User (Peer-Auth), Dump au\xdferhalb des Rootfs:
   su - postgres -c "pg_dump -Fc hcc" > /var/backups/hcc-$(date +%F).dump
   ```
   (Retention/Rhythm = Betriebsaufgabe; automatisches Backup ist R2-Kandidat,
   D-I2 — R1 hat bewusst keinen pg_dump-Timer.)
3. **Secrets getrennt sichern:** `/etc/hcc/hcc.env`, `/etc/hcc/.pg_password`,
   `/etc/hcc/secrets.env` (falls vorhanden) — verschlüsselt, **nicht** auf
   dem PVE-Backup-Storage im Klartext, Zugriff nur für den Betreiber.
4. **Restore-Test (einmalig):** CT-Backup auf separatem Testsystem bzw.
   temporär anfreuen + pg_dump in eine Test-DB laden — dokumentieren
   (Abnahmekriterium, `R1-acceptance-checklist.md`).

---

## 9. Deployment: `scripts/deploy-lxc.sh` (Stufen 0–7)

**Status des Skripts:** statisch vollständig reviewed; in dieser Umgebung
nicht ausführbar (Linux-only). **R1-Validation-Fixes sind in diesem Branch
enthalten:** V-1/V-2 (hcc.env-Generierung), V-6 (`npm ci`), V-7 (nginx
Keepalive), V-8 (Lockfile im Preflight).

**Voraussetzungen im LXC:**
- Git-Checkout des Deployment-Branches (sauber; `deploy-lxc.sh` deployt
  `git archive HEAD`, dirty Worktree → Warnung).
- Node.js ≥ 20.19 manuell installiert (aus geprüftem Repository;
  bewusst kein apt-Pin — D5). Ohne Node wird das Frontend nicht gebaut
  (klare Warnung, nginx liefert bis dahin kein SPA).
- Python-Toolchain: das Skript stellt `uv` her (via pip in
  `/opt/hcc/tools/uv` — kein `curl | sh`), Venv kommt aus `uv.lock`.

**Aufruf:**
```bash
# im LXC, root, nach Abschluss des Release-Downloads:
sudo scripts/deploy-lxc.sh /pfad/zum/checkout --start
```

| Stufe | Inhalt (idempotent) |
| --- | --- |
| 0 — Preflight | Alle Artefakte im Checkout vorhanden (inkl. `frontend/package-lock.json`, Fix V-8); Git-Checkout; uncommittete Änderungen → Warnung |
| 1 — Pakete | `apt-get` (Debian-Pakete): ca-certificates, git, nginx, postgresql, python3, python3-venv, openssl — **kein** Node (D5) |
| 2 — uv | vorhanden? ja: nutzen; nein: venv + pip-install nach `/opt/hcc/tools/uv` |
| 3 — Identität/Verzeichnisse | System-User `hcc` (nologin), `/opt/hcc/*`, `/etc/hcc`, `/var/lib/hcc`, `/var/log/hcc` |
| 4 — PostgreSQL | Rolle `hcc` (LOGIN, kein Superuser) + DB `hcc`; Passwort einmalig via `openssl rand -hex 24` → `/etc/hcc/.pg_password` (0600); Peer-Auth für psql-Prüfungen; PG bleibt an lokalem Socket/Loopback |
| 5 — Release | `git archive HEAD` → `/opt/hcc/releases/<sha>`; Backend-Venv via `uv sync --frozen`; Frontend via **`npm ci`** (Fix V-6) + `npm run build`; atomares `current`-Symlink |
| 6 — hcc.env | aus `.env.example` + sed (Fix V-1/V-2): **Inline-Kommentare entfernt**, `HCC_ENVIRONMENT=production`, `HCC_COOKIE_SECURE=true`, `HCC_DATABASE_URL` mit PG-Passwort, `HCC_GIT_COMMIT=<sha>`, `HCC_CORS_ORIGINS=[]`; Bootstrap-Token einmalig via `openssl rand -hex 24`; `0640 root:hcc` |
| 7 — systemd+nginx | `health-probe.sh` nach `/usr/local/lib/hcc/`, Unit installieren/enable, nginx-Site + `nginx -t` + Reload/Start |

**Warum die hcc.env-Generierung korrigiert werden musste (Fix V-1/V-2,
Validierungsnachweis):** systemd-`EnvironmentFile` streicht keine
Inline-Kommentare; `.env.example` enthält `HCC_SESSION_TTL_SECONDS=43200
# 12 h …` → der Wert hätte den Kommentar enthalten → pydantic-Int-Parsecrash
beim App-Start. Empirisch reproduziert: `Settings()` mit diesem Wert →
`ValidationError`. Gleiches für `HCC_CORS_ORIGINS=` (leer):
pydantic-settings erwartet für das `list[str]`-Feld JSON; die leere Zeichenkette
bricht das Parsing (empirisch: `json.JSONDecodeError`). Die korrigierte
Pipeline wurde 1:1 simuliert (sed-Ausdrücke auf `.env.example` angewendet) und
das Ergebnis gegen `app.config.Settings()` validiert: **Start ohne Fehler**
(environment=production, cookie_secure=true, ttl=43200, cors=[]).

**Bootstrap-Token-Handling (D3):** Das Token bleibt nach Nutzung in
`/etc/hcc/hcc.env`. Rotation ist ein Betriebsschritt (neuen Wert in der Datei
setzen + `systemctl restart hcc-api`); solange User existieren, wird
`/auth/bootstrap` ohnehin abgelehnt.

---

## 10. PostgreSQL und Migration

- **Instanz:** lokales Debian-Paket, nur Socket/Loopback (Default-Konfiguration
  des Pakets; keine `listen_addresses`-Erweiterung).
- **Rolle:** `hcc` — LOGIN mit lokalem Passwort, **kein Superuser**, Owner der
  DB `hcc`. (Stufe 4 von `deploy-lxc.sh`.)
- **Migration:** ausschließlich über systemd —
  `ExecStartPre=/opt/hcc/current/backend/.venv/bin/alembic upgrade head`
  (Gate 12 prüft: `deploy-lxc.sh` führt **keine** top-level-`alembic`-Befehle
  aus). Idempotent; vor jeder App-Start.
- **R1-Status der Migration:** exakt eine Migration (`0001_initial`) — kein
  Schema-Drift zwischen Release-Kandidaten, solange keine neue Migration
  zwischen deployed und Ziel-Release liegt (Rollback-Bedingung, s.
  `R1-rollback.md`).
- **Live-Evidenz:** `alembic upgrade head` wurde in der Validierung auf einer
  temporären SQLite-DB ausgeführt (grün). Der **PostgreSQL-Live-Roundtrip**
  (`test_postgresql_live_migration_roundtrip`) ist in dieser Umgebung nicht
  ausführbar (kein PG) → im Ziel-LXC durch `ExecStartPre` + Health-Probe-Gate
  abgedeckt (erst ein `health/live`-200 zählt als erfolgreicher Start).
- **Kandidat für R2 (V-9):** Die Migration erzeugt auf SQLite
  `audit_events.id` als `BIGINT` (kein rowid-Alias) → INSERTs schlagen dort
  fehl (empirisch in der Validierung). Auf PostgreSQL lautet das DDL
  `id BIGSERIAL NOT NULL` (Sequence, funktional korrekt — per DDL-Rendering
  gegen den PostgreSQL-Dialekt nachgewiesen). Dev-Workflow mit
  `alembic upgrade head` auf SQLite ist also gebrochen; Tests verwenden
  ORM-`create_all` (INTEGER PRIMARY KEY, funktioniert). Kein
  Produktionsblocker, R2-Fix-Vorschlag (z. B. Integer/BigInteger-
  Dialektbehandlung oder SQLite-relevantes `INTEGER PRIMARY KEY`).

---

## 11. Systemdienst `hcc-api.service` und nginx

**`hcc-api.service` (eingefrorenes Deployment-Vertrag, `deploy/systemd/hcc-api.service`):**

| Eigenschaft | Wert |
| --- | --- |
| Identität | `User=hcc` / `Group=hcc` (unprivilegiert, nologin) |
| Bind | nur `127.0.0.1:8000` |
| Environment | `EnvironmentFile=/etc/hcc/hcc.env` + optionales `/etc/hcc/secrets.env` |
| Vor-Start | `ExecStartPre=…/alembic upgrade head` |
| Start | `uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000` |
| Nach-Start | `ExecStartPost=/usr/local/lib/hcc/health-probe.sh` (30 s Poll auf `health/live`-200; Start zählt erst bei Erfolg) |
| Resilienz | `TimeoutStartSec=180`, `Restart=on-failure`, `RestartSec=5` |
| Hardening | `NoNewPrivileges`, `PrivateTmp`, `PrivateDevices`, `ProtectSystem=full`, `ProtectHome`, `ProtectKernelTunables/Modules/Logs`, `ProtectControlGroups`, `ProtectClock`, `ProtectHostname`, `RestrictSUIDSGID`, `RestrictRealtime`, `LockPersonality`, `RemoveIPC`, `UMask=0027` — bewusst **keine** `PrivateNetwork` (lokales PG) |
| Docker-Socket | kein Bezug (Gate 12 prüft) |

**nginx (`deploy/nginx/hcc.conf`):**
- `listen 127.0.0.1:8080` (Loopback; Tailscale Serve leitet dorthin).
- Upstream `hcc_api` → `127.0.0.1:8000`, `keepalive 32` **plus
  `proxy_set_header Connection ""`** (Fix V-7, R1-Validation: ohne das
  Header-Setzen sendet nginx `Connection: close` an den Upstream und die
  Keepalive-Pool-Verbindung wird nie genutzt — nginx-Doku `keepalive_Requirements`).
- `proxy_http_version 1.1`, `proxy_buffering off`, `proxy_read_timeout 120s`
  (SSE-Readiness), Sicherheits-Header (nosniff/DENY/no-referrer),
  `server_tokens off`.
- SPA: `root /opt/hcc/current/frontend/dist`, `/assets/` mit
  `Cache-Control: public, immutable`, SPA-Fallback `try_files … /index.html`.

**Validierung in dieser Umgebung:** nginx-Konfiguration statisch geprüft +
Gate 12 (Deploy-Invarianten) grün nach dem Fix. `nginx -t`/Reload: nicht
durchgeführt (kein Linux).

---

## 12. Ersteinrichtung: Admin-Bootstrap (einmalig)

**Nur vor der ersten Nutzung, nur solange keine User existieren** (danach
wird der Endpunkt dauerhaft abgelehnt):

```bash
# im LXC (oder via Tailscale-Serve), Token aus /etc/hcc/hcc.env lesen:
TOKEN="$(grep '^HCC_BOOTSTRAP_TOKEN=' /etc/hcc/hcc.env | cut -d= -f2)"
curl -fsS -X POST http://127.0.0.1:8080/api/v1/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<gewaehlt-passt-langes-Passwort>","token":"'"$TOKEN"'"}'
```

- Ergebnis: `201` + Admin-User angelegt (Evidenz aus der Validierung:
  `{"username":"admin","message":"Initialer Admin angelegt. …"}`).
- Die API antwortet mit „Passwort vor erster Nutzung ändern" — die
  Passwortwechsel-API ist in R1 aber **blockiert** (Proposal
  `backend-auth-change-password.md` offen; `PATCH /users/{id}` akzeptiert nur
  `role`/`is_active`/`display_name`, kein Passwortfeld). **Konsequenz:**
  das Bootstrap-Passwort wird lang und eindeutig gewählt und vom Betreiber
  sicher verwaltet, bis die Passwortwechsel-API (R2) existiert.
- **Verlust des Admin-Passworts (R1-Betriebsumweg, dokumentiert):**
  Die Service-Funktion `app.users.service.change_password` existiert
  (Argon2id-Prüfung, Session-Revocation, Audit — getestet in der
  Backend-Suite), ist aber in R1 **bewusst nicht als REST-Endpunkt
  exponiert** (Proposal `backend-auth-change-password.md` offen).
  Betriebsumwege: (a) kleines Admin-Skript im Release-Venv, das die
  Service-Funktion aufruft; (b) `password_hash` direkt in der DB neu
  setzen (als `postgres`-User; Hash-Format = Argon2id, s.
  `app/auth/hashing.py`); (c) bei neuem Setup: User-Zeile entfernen,
  damit `/auth/bootstrap` wieder frei ist (bootstrap ist nur möglich,
  solange keine User existieren). Es gibt bewusst kein DELETE-User-API;
  Last-Admin-Guard: der letzte aktive Admin darf nicht deaktiviert/
  heruntergestuft werden (`update_user`).
- Danach: Smoke-Test (Abschnitt 13) mit den echten Admin-Credentials.

---

## 13. Abnahme und Healthchecks

### 13.1 Abnahme-Ablauf (im Ziel-LXC, nach `deploy-lxc.sh --start`)

```bash
# 1) Service-Zustand
systemctl --no-pager status hcc-api.service --lines=15
journalctl -u hcc-api --since "-10min" | tail -n 30

# 2) Healthchecks (Produktionspfad über nginx)
curl -fsS http://127.0.0.1:8080/api/v1/health/live     # 200 ok
curl -fsS http://127.0.0.1:8080/api/v1/health/ready    # 200 (DB-Check ok)
curl -fsS http://127.0.0.1:8080/api/v1/version         # {"commit":"<sha>",…}

# 3) E2E-Smoke (8 Schritte + Aufräum; Credentials ohne Default)
export HCC_SMOKE_ADMIN=admin
export HCC_SMOKE_PASS='<admin-passwort>'
sudo bash tests/e2e/e2e-smoke.sh                        # Exit 0 = alle OK
```

**Status:** nicht durchgeführt (kein Ziel-LXC). Die E2E-Schritte wurden in der
Validierung gegen eine lokale Dev-Instanz (SQLite) als **Ersatz-Evidenz**
real ausgeführt — s. 13.3.

### 13.2 Abnahmekriterien (verbindlich)

Alle `R1-acceptance-checklist.md`-Punkte grün, insbesondere:
- Smoke 8/8 + Aufräum (Test-Viewer deaktiviert)
- `health/ready` 200 (DB erreichbar)
- `version.commit` == deployed Commit
- Tailscale-Erreichbarkeit + TLS vom Admin-Device
- Backup-Strategie aus Abschnitt 8 einmal ausgeführt + Restore-Test
- Rollback-Vorbereitung: `deploy-lxc.sh --list` zeigt ≥ 1 Release
- Datei-Rechte: `hcc.env` 0640 root:hcc, `.pg_password` 0600 root

### 13.3 Validierungsnachweis (real ausgeführt, lokale Dev-Instanz)

Gegen eine lokal laufende R1-Instanz (SQLite, `127.0.0.1:8123`,
Produktions-Code aus dem Branch) wurden die Smoke-Semantiken real geprüft:

| Schritt | Ergebnis (Evidenz) |
| --- | --- |
| `health/live` | `200 {"status":"ok","service":"hcc-api","version":"0.1.0",…}` |
| `health/ready` | `200` mit `checks: [{name:"database","status":"ok",…}]` |
| `version` | `{"name":"hcc-api","version":"0.1.0","release":"R1","commit":"validation-test"}` — **Fix V-3 bewiesen:** Feld heißt `commit`, nicht `git_commit` (frozen Contract `VersionResponse`) |
| `openapi.json` | erreichbar, `openapi: 3.1.0` |
| Login | `set-cookie: hcc_session=…; HttpOnly; …; SameSite=lax` + `set-cookie: hcc_csrf=…; SameSite=lax` |
| Cookie-Jar | **Fix V-4 bewiesen:** Netscape-Tab-Format (`127.0.0.1  FALSE  /  FALSE  <exp>  hcc_csrf  <wert>`); die alte `grep -o 'hcc_csrf=[^;]*'` kann nie matchen; korrekte awk-Extraktion (`$6=="hcc_csrf" → $7`) liefert den Token |
| CSRF-Matrix | POST ohne `X-CSRF-Token` → **403**; mit Token → **201** (User angelegt) |
| RBAC | Viewer: POST `/users` → **403**; GET `/audit` → **403**; Admin: PATCH `is_active=false` → **200**; deaktivierter Viewer (alte Session) auf `/auth/me` → **401** |
| Error-Envelope | 404 → `{"error":{"code":"not_found","message":"Not Found","details":null,"request_id":"…"}}` |
| hcc.env-Generierung | alte Pipeline → pydantic-Crash (V-1/V-2 empirisch); **neue Pipeline → `Settings()` startklar** (simulierte 1:1-Übersetzung der sed-Ausdrücke, validiert) |

**Bekannter Umwelteinfluss (kein Produktdefekt):** auf der **SQLite**-
Validierungs-DB bricht ein via Alembic migrierter Audit-Insert (V-9);
Workaround nur für die Validierungs-DB, auf PostgreSQL ist das DDL korrekt
(BIGSERIAL). Die Produktiv-Instanz (PostgreSQL) ist davon nicht betroffen.

### 13.4 Healthchecks im Betrieb

- **Start-Gate:** `ExecStartPost`-Health-Probe (30 s) — Start zählt erst bei
  `health/live`-200.
- **Readiness:** `health/ready` prüft die Datenbank (`SELECT 1`-Pfad,
  Duration-Field im JSON).
- **Betriebsüberwachung (R2-Kandidat D-I3):** `After=postgresql.service` ohne
  `Requires=` — ein PG-Stillstand führt zu App-500ern, nicht zu einem
  Service-Neustart. Für R1 akzeptiert (Homelab-Scope); Monitoring-Anbindung
  als R2.

---

## 14. Rollback (Kurzfassung)

Detailliert: **`docs/deployment/R1-rollback.md`**.

- **Anwendungsebene:** `sudo scripts/deploy-lxc.sh --list` (Releases
  überschauen) → `sudo scripts/deploy-lxc.sh --rollback <commit-sha>`
  (atomarer Symlink-Tausch + `systemctl restart hcc-api` + Health-Probe).
  Nur für bereits deployte Releases.
- **Daten:** Rollback deckt **keine** Datenänderungen ab — neue User/
  Integrations-/Audit-Rows bleiben. In R1: kein Schema-Drift (eine Migration),
  daher ist App-Rollback ohne DB-Aktion sicher.
- **Ganze-CT-Ebene:** PVE-CT-Backup-Restore (Abschnitt 8) für schwerwiegende
  Fälle (defektes Rootfs, kaputte Konfiguration) — RTO/RPO s. Rollback-Doku.

---

## 15. Troubleshooting und Betriebsnotizen

| Symptom | Ursache-Check | Maßnahme |
| --- | --- | --- |
| `hcc-api.service` startet nicht, `journalctl` zeigt Alembic-Fehler | PG nicht erreichbar / Rolle fehlt / Migration bricht | PG-Status (`systemctl status postgresql`), Rolle/DB per Peer-Auth prüfen; dann erneut starten (`ExecStartPre` läuft neu) |
| Service „started", aber Port 8000 nicht erreichbar | Health-Probe > 30 s | `journalctl -u hcc-api` (Tracebacks), `systemctl show hcc-api -p Result` |
| Login → HTTP 429 nach wenigen Versuchen | In-memory-Rate-Limit (10/60 s **pro Loopback-IP**, S3) | gewartet oder Bucket-Reset (Service-Neustart); Multi-Admin-Betrieb: R2-Fix (S3) |
| Frontend leer, nur API läuft | `frontend/dist` nicht gebaut (Node fehlte beim Deploy) | Node ≥ 20.19 installieren, `deploy-lxc.sh` neu ausführen (Stufe 5 baut bei fehlendem `dist`) |
| Bootstrap abgelehnt | User existieren bereits (einmalig) | erwartet — keine Aktion; Admin-Zugang über Login |
| `health/ready` → 503 | DB-Check schlägt fehl | PostgreSQL + Rolle `hcc` prüfen; `HCC_DATABASE_URL` in `/etc/hcc/hcc.env` |
| TLS-Fehler vom Admin-Device | Tailscale Serve-Adresse/Zertifikat | Tailscale Serve-Konfiguration prüfen; `tailscale status` |
| 500er bei aktiver API, PG down | D-I3 (`After=` ohne `Requires=`) | PG hochfahren; App-Requests erholen sich selbst (keine Session-/State-Korruption); R2: `Requires=`/Monitoring |
| Unvorhersehbares Cookie-/Session-Verhalten | `hcc.env`-Wert fehlerhaft (z. B. TTL) | `hcc.env` gegen `.env.example`-Semantik prüfen (keine Inline-Kommentare — Fix V-1) |
| Deployment bricht im Preflight | unvollständiges Checkout / kein Git | Checkout prüfen (`git status`), sauberen Stand beziehen |

**Betriebsnotizen:**
- Logs: `journalctl -u hcc-api` (App-Logs, structured JSON via uvicorn-log-
  handler), nginx-Logs standardmäßig `/var/log/nginx/`.
- Release-Hygiene: alte Releases unter `/opt/hcc/releases/` bei Bedarf
  manuell entfernen (mindestens das zweite-neueste behalten), um Rootfs
  nicht aufzublähen (16 GiB Startwert).
- Updates: neuer Branch/Commit → Checkout → `deploy-lxc.sh <checkout> --start`
  → Smoke → erst dann alt-Release entfernen.
- **Kein** Docker-Socket, **keine** offene Shell-API, **keine**
  WAN-Portfreigaben — bei Änderungswünschen: Playbook + Sicherheits-Review
  aktualisieren (AGENTS.md-Regel 4: Contracts/Änderungen über
  `docs/proposals/`).
