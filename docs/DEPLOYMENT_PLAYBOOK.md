# Deployment- und OpenCode-Playbook — HCC 2.0

**Status:** ausführbare Vorbereitungsbefehle + Sollstruktur. Konkrete systemd-Startmodule/DB-Migrationen werden erst durch den Foundation-Agent implementiert; im Playbook ausdrücklich markiert. Nicht als fertiges Deployment-Skript ausgeben.

## 1. Zielumgebung und Annahmen
- Proxmox VE auf bekanntem i7-4790-System, insgesamt 32 GB RAM. [Nicht verifiziert] Verfügbare Kapazität, Host-Storage, PVE-Version, Bridges, aktive CT-IDs, externe API-Dienste.
- HCC läuft in eigenem **unprivilegiertem** Debian-LXC, kein Docker innerhalb des LXC erforderlich.
- Startgröße als **Planungswert, nicht Messwert**: 2 vCPU, 3 GiB RAM, 16 GiB Rootfs; bei lokalem PostgreSQL und viel Event-Retention ggf. 4 GiB/32 GiB. Monitoring-Prometheus/Grafana wird nicht im HCC neu installiert.
- HCC über LAN mit optionalem Tailscale-IP/MagicDNS, erreichbar nach Authentifizierung. Keine WAN-Portweiterleitung.
- Folgende Werte **vor Benutzung ersetzen**: `CTID=240`, `VM_BRIDGE=vmbr0`, `STORAGE=local-lvm`, `DEBIAN_TEMPLATE=<exact-file>`, DNS/Netzwerk. Keine garantierte Eignung dieser Beispielwerte.

## 2. Preflight auf Proxmox-Host (nur lesend)
```bash
pveversion -v
pct list
pvesm status
ip -br addr
free -h
pveam available --section system | grep -E 'debian-13|debian-12' | head
```

Prüfen: CPU/RAM frei, LXC-ID frei, Storage verfügbar, DNS erreichbar, Default-Gateway, IPv4-Verfahren (DHCP/statisch), Backup-Speicher und PVE-Firewall. Debian-Version/Template entsprechend deiner Proxmox-Version verifizieren. Nicht blind auf Produktionshost ausführen.

## 3. LXC erzeugen (erst nach Freigabe; Beispiel)
```bash
# Auf dem Proxmox-Host; EXAMPLE values deliberately explicit
CTID=240
STORAGE=local-lvm
VM_BRIDGE=vmbr0
DEBIAN_TEMPLATE='local:vztmpl/<exact-debian-template>.tar.zst'

# Template muss zuvor korrekt heruntergeladen und unter dem angegebenen Pfad vorhanden sein.
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
**Hinweise:** `nesting=0` ist nur der Ausgangswert; vor produktiver Nutzung prüfen, ob einzelne systemd-/Isolation-Funktionen Änderungen benötigen. Kein Privileged-Container, keine Abschaltung von AppArmor. `local-lvm` und CTID sind Beispiele, keine überprüfte Umgebung.

## 4. Tailscale im unprivilegierten LXC
Laut offizieller Tailscale-Anleitung kann Proxmox `/dev/net/tun` in einen unprivilegierten LXC durchreichen. Auf **Proxmox-Host** nach Freigabe:
```bash
pct shutdown 240
pct set 240 --dev0 /dev/net/tun
pct start 240
pct exec 240 -- ls -l /dev/net/tun
```
Falls `pct set --dev0` in der eingesetzten PVE-Version nicht unterstützt wird: Proxmox UI > CT > Resources > Add > Device Passthrough; `/dev/net/tun` auswählen. Keinesfalls automatisch weitreichende LXC-Rechte gewähren.

Im **LXC** nach Prüfung des offiziellen Installationsverfahrens:
```bash
apt update
apt install -y curl ca-certificates
# Vor Ausführung offiziellen Tailscale-Installationsweg und Paketsignaturen prüfen.
# Kein ungeprüftes remote curl|sh als Default.
# Nach Installation:
tailscale up --accept-routes=false --advertise-exit-node=false
tailscale status
```
Tailscale-ACL/Grants: nur persönliche Admin-Geräte dürfen HCC erreichen, keine Exit-Node/Subnet-Router-Funktionen aktivieren. Prüfen, ob Pi-hole/MagicDNS/resolv.conf im LXC konsistent sind.

## 5. Pakete und Systemdienste (im LXC)
```bash
apt update
apt install -y ca-certificates git curl nginx postgresql python3 python3-venv python3-pip
# Node.js aus einem gewarteten, geprüften Repository für Frontend-Build installieren;
# Version gemäß foundation package.json / Lockfile festlegen.
# Keine systemweite pip install-Ausführung gegen distribution-managed Python.
```
**Sollverzeichnisse:** `/opt/hcc/releases/<version>/backend`, `/opt/hcc/releases/<version>/frontend`, `/opt/hcc/current` (Symlink), `/etc/hcc/hcc.env` (root/Servicegruppe, 0640), `/var/lib/hcc`, `/var/log/hcc`. Separate unprivilegierte Serviceidentität `hcc`; nginx als Reverse Proxy zu FastAPI auf `127.0.0.1:8000`. Das Backend muss nur über Loopback lauschen. App-Datenbank mit dediziertem PostgreSQL-User, keine Superuser-Rolle.

**Achtung:** Die vollständigen produktiven Befehle für `hcc-api.service`, den initialen Admin, Alembic-Migration und Frontend-Build **können erst nach Erstellung des Repositories** seriös festgelegt werden. Der Foundation-Agent muss eine geprüfte, idempotente Datei `scripts/deploy-lxc.sh` und zwei systemd-Unit-Dateien erstellen. Keine Platzhalter als angeblich lauffähige Kommandos übernehmen.

## 6. Systemd-Kontrakt (vom Foundation-Agent implementieren)
- `hcc-api.service`: `User=hcc`, `Group=hcc`, `WorkingDirectory=/opt/hcc/current/backend`, `EnvironmentFile=/etc/hcc/hcc.env`, bind an `127.0.0.1:8000`, `Restart=on-failure`, `NoNewPrivileges=yes`, systemd hardening soweit ohne Funktionsbruch möglich.
- `nginx`: statisches SPA-Build aus `/opt/hcc/current/frontend/dist`, `/api/` an loopback Backend, sane timeouts, Headers, WebSocket/SSE falls erforderlich.
- CORS restriktiv, Cookies bei HTTPS Secure/HttpOnly/SameSite; kein öffentliches Admin-API.
- TLS: bevorzugt Tailscale Serve oder einen klar dokumentierten internen HTTPS-Reverse-Proxy; vor Produktivbetrieb testen, welche Adresse/Cert-Funktion real verfügbar ist. HTTP allenfalls im isolierten Testnetz.
- PostgreSQL: nur lokal erreichbarer Socket/Loopback, rollenbasierte DB-Credentials, Backups getrennt vom LXC-Rootfs.

## 7. API-Zugriff und Berechtigungen
- **Proxmox:** eigener API-Token; initial nur Auditrechte; der Agent dokumentiert tatsächlich benötigte Privileges pro Endpoint. Für VM-Lifecycle separat auf eng definierten Pool/VMs beschränkte Rolle, kein Root-Token.
- **TrueNAS, Pi-hole, Docker, Tailscale:** dedizierte read-only Zugänge, versionierte API-Tests, TLS-Zertifikatsprüfung aktiv. Kein globaler Docker-Socket-Mount, keine offenen unverschlüsselten Remote-Docker-Ports.
- **Monitoring:** Prometheus read-only query; Grafana nur falls bereits vorhanden; keine automatische Stack-Installation; Source-Freshness/Units immer anzeigen.
- Externe Endpoints durch Admin konfiguriert, gegen SSRF/unerlaubte Ziel-IP und Redirects absichern.

## 8. OpenCode-Projekt lokal initialisieren
```bash
mkdir -p ~/projects/homelab-control-center
cd ~/projects/homelab-control-center
git init -b main
# Den Inhalt des ZIP-Pakets HIERHIN kopieren, sodass AGENTS.md im Repo-Root liegt.
git add AGENTS.md MASTER_PROMPT.md docs agent-tasks
git commit -m 'docs: initialize HCC architecture and agent playbooks'
opencode
```
**Foundation-Prompt in Session 0:** `Lies AGENTS.md, MASTER_PROMPT.md, docs/PARALLEL_WORKFLOW.md und docs/DEPLOYMENT_PLAYBOOK.md. Implementiere ausschließlich Release R0 Foundation. Definiere und teste gemeinsame Contracts. Committe die Arbeit und liefere einen Übergabebericht. Kein Deployment in reale Infrastruktur.`

Foundation-Agent muss `docs/architecture.md`, `docs/api-contracts.md`, `docs/foundation-handoff.md` und initiale Tests erzeugen; die in `docs/PARALLEL_WORKFLOW.md` definierten Verzeichnisse fixieren. Dann den Foundation-Branch überprüfen und in `main` integrieren.

## 9. Fünf Sessions parallel
Ab jetzt `docs/PARALLEL_WORKFLOW.md` ausführen. Git-Worktrees isolieren den Dateistand, nicht die gemeinsame Modell-GPU, Credentials oder externe Dienste. Pro Session: `opencode` aus ihrem eigenen Verzeichnis. In jeder Session den passenden `agent-tasks/0X-*.md`-Auftrag geben. Agents dürfen nur ihren Branch committen; Merges durch Betreiber nach Review. Vor fünf parallelen Sessions mit zwei Sessions Latenz und Stabilität prüfen.

## 10. Release-, Monitoring- und Recovery-Prüfung
- Source-Code-Build und Typechecks
- DB-Migration gegen neue Testdatenbank
- Backend Unit-/Integrationstests
- Frontend Unit-/E2E-Tests
- Security-Tests, RBAC/CSRF/Auth/Secret-Scanning
- Live-Proxmox-Read-only-Smoke-Test nach Freigabe
- Tailscale-Zugriff und lokaler Zugriff mit gültigem Benutzer
- Nicht erreichbare Integrationen legen keine UI/API-Operationen lahm
- Backup, Restore auf separates Testsystem, Upgrade und Rollback dokumentieren
- Proxmox-CT-Backup **plus** konsistenter PostgreSQL-Dump, Restore-Test; Secrets getrennt sichern

## 11. Messungen und klare Grenzen
- HCC braucht **keine lokale GPU**; GPU wird nur beim OpenCode-Coding durch LLM-Inferenz belastet.
- LXC-Größen sind Planungswerte. Nach R0 und R1 RSS, CPU, I/O und Datenbankgröße messen und anpassen.
- Kein echter Infrastruktur-Zugriff ist hier geprüft. `Proxmox`, `TrueNAS`, `Pi-hole`, `Tailscale` müssen mit bereitgestellten Endpunkten und credentials validiert werden.

## Referenzen
- https://pve.proxmox.com/pve-docs/
- https://tailscale.com/docs/features/containers/lxc/lxc-unprivileged
- https://opencode.ai/docs/instructions/
- https://opencode.ai/docs/cli/
