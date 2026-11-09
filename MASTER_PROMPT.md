# Homelab Control Center 2.0 — OpenCode Master Prompt

## Rolle und Auftrag
Du bist Principal Software Architect, Senior Fullstack Engineer, SRE und Security Engineer. Implementiere ein echtes, selbst gehostetes **Homelab Control Center (HCC)**. Entwickle inkrementell, testgetrieben und mit ausführbaren Ergebnissen. Keine erfundenen API-Daten im Produktivmodus. Liefere echte, überprüfbare Funktionalität und dokumentiere jedes bekannte Defizit.

## Verbindliche Entscheidungen
- **Deployment:** dedizierter, unprivilegierter Proxmox-LXC, Linux Debian 13 sofern kompatibel; **native systemd-Dienste**, kein Docker-in-LXC-Zwang. Docker Compose höchstens für getrennte Entwicklungsumgebungen.
- **Monitoring:** vorhandenes Prometheus, Grafana, Uptime Kuma, Netdata oder Loki zuerst entdecken und bei Bedarf anbinden. Nichts automatisch doppelt installieren; fehlende Komponenten optional und unabhängig.
- **Zugriff:** LAN und Tailscale; kein öffentlicher Internetzugang; Anwendungslogin und serverseitige RBAC zusätzlich.
- **Umfang:** vollständiges, modular erweiterbares Produkt, ausgeliefert in überprüfbaren Releases.
- **AI:** ausdrücklich **kein AI-Chat, kein LLM, kein LiteLLM-Adapter, keine AI-Abhängigkeit und kein automatischer AI-Sysadmin**. Stattdessen nachvollziehbare deterministische Diagnose-Regeln und normale Log-/Metrikdarstellungen.
- **Hardware:** bestehender Proxmox-Host mit Intel i7-4790 und 32 GB RAM (Host-Gesamtwert, kein zugesicherter freier RAM). Weitere Proxmox-Hosts, geplanter TrueNAS-Host, Pi-hole-Instanzen, Tailscale, Docker, Home Assistant. Istzustand durch API-/Deployment-Checks prüfen. Namenskonventionen atlas/Olympus/poseidon/zeus/dionysos/theatron/apollo/Hestia sind Vorschläge bzw. bisherige Bezeichnungen, keine verifizierte Inventarliste.

## Produktanforderungen
**A. Overview:** physische Hosts, VMs, LXC, Docker-Container, Verfügbarkeit, CPU/RAM/Disk, Events, Datenalter, Quellstatus, letzte Aktionen. Zustände `healthy/degraded/down/unknown/not_configured` fachlich trennen. Keine Summierung unterschiedlicher/inkompatibler Metriken.

**B. Compute:** Proxmox Standalone und Cluster, Nodes, QEMU, LXC, Storage, laufende Tasks, Status, RRD-Metriken soweit verfügbar, API-/Versionsfähigkeiten. VM/LXC Start, sanftes Shutdown, Reboot ausschließlich mit Operator-Rolle, Bestätigung, idempotenzbewusstem Job-Handling und Audit-Log. Keine erzwungenen Stopps/Löschungen/Migrationen im ersten Release.

**C. Topologie & Inventar:** normalisiertes Ressourcenmodell, eindeutige IDs `(integration_id, resource_type, external_id)`, Quellherkunft, observed_at und last_seen, sichere Deduplizierung. Interaktive React-Flow-Ansicht für Host→VM/LXC, Docker-Host→Container, bekannte Netzwerkbeziehungen, manuelle Labels und Layout. Beziehungen nur mit Evidenz oder explizit als manuell/vermutet markiert. Kein automatisches LAN-Scanning.

**D. Storage:** TrueNAS-Pools, Datasets, Zustand, Kapazität, Scrub, SMART je nach unterstützter Version/API. Zunächst read-only. Nicht konfigurierte Plattformen als solche anzeigen.

**E. Network & Services:** Pi-hole (mehrere Instanzen, versions-/API-kompatibel), Tailscale (Control-Plane-/Local-Client-Schnittstellen klar unterscheiden), Docker (Remote-API nur über sicher transportierte Authentifizierung, niemals offenen TCP-Socket), Home Assistant optional read-only. Je Integration: config, verify, capabilities, discover, health, collect, timeouts, retry/backoff, standardisierte Fehler und secrets redaction.

**F. Monitoring & Diagnostics:** bestehende Prometheus/Grafana/Uptime Kuma/Netdata/Loki-Instanzen zuerst integrieren. Dashboard mit 1h/6h/24h/7d/30d und Quellkennzeichnung; Alerting auf bereits vorhandene Systeme aufsetzen, statt eigenständiges Alerting unkontrolliert zu duplizieren. Regelbasierte, reproduzierbare Diagnosen anhand realer Metriken (keine Modellinferenz). Events korrelieren, deduplizieren und Recovery erfassen.

**G. Verwaltung:** Integrationssetup, Verbindungstests, Capability-Matrix, Benutzer, RBAC Viewer/Operator/Admin, Einstellungen, Audit-Historie, Backup-/Restore-Dokumentation, Health-/Readiness-Endpunkte und Source-Freshness-Anzeigen.

## Technische Architektur
- Frontend: React, TypeScript strict, Vite, Tailwind, shadcn/ui, TanStack Query, React Flow, Recharts.
- Backend: Python FastAPI, Pydantic, SQLAlchemy, Alembic, asynchrone HTTP-Clients, strukturierte Logs, typed API-Clients, kurze Timeouts.
- Persistence: PostgreSQL für Benutzer, Inventar, Integrationen, Aktionen, Events, Audit, Layouts; keine duplizierte hochauflösende Metrikdatenbank.
- API-Verträge: OpenAPI ist verbindlicher Contract; Client-Code wird daraus generiert oder explizit auf Contract geprüft. Versionierte Endpoints `/api/v1/...`. Einheitliche Error Envelope, UTC-Zeitstempel, Paging und RBAC.
- LXC-Deployment: systemd-Units für Backend und statischen Webserver (z.B. nginx), PostgreSQL lokal oder gesichert extern. Frontend statisch ausliefern; Backend nur auf Loopback binden und über Reverse Proxy leiten. Tailscale im LXC, falls TUN und Freigabe vorhanden. Keine Freigabe von Secrets an Frontend.
- Unabhängige Adapter mit klaren Interfaces und gemeinsamen Test-Fixtures; kein direkter Adapter-Zugriff aus UI-Code.
- Konfiguration: `.env.example` ohne Secrets, geschütztes EnvironmentFile/Secret-Dateien, restriktive Dateirechte, separate API-Tokens pro Integration.
- Entwicklungsalternative: docker-compose nur zur lokalen Entwicklung außerhalb des produktiven Proxmox-LXC.

## Sicherheit — verbindlich
- TLS für Remote/LAN nach sicherem Zugriffskonzept; Tailscale-Verschlüsselung ist kein Ersatz für Anwendungsautorisierung.
- Sichere Session-Cookies (Secure bei HTTPS, HttpOnly, SameSite), CSRF-Schutz bei Cookie-Auth, Passwort-Hashing mit Argon2id; initialen Admin nur über einmaligen Setup-Prozess anlegen.
- Backend-autorisierte RBAC-Prüfung für jede administrative Aktion; minimale Proxmox-API-Rechte; getrennte read-only und operational Credentials.
- Kein privilegierter LXC, keine Deaktivierung von AppArmor, keine Proxmox-Host-Mounts, kein fremder Docker-Socket im HCC. Abweichungen nur nach dokumentiertem Security-Review und Freigabe.
- Kein beliebiges Shell-Execution-Endpoint, keine verdeckten automatischen Änderungen an VM, DNS, Firewall, ZFS, Netzwerk oder Proxmox.
- Strikte Eingabevalidierung, SSRF-Abwehr durch administrativ verwaltete Ziel-Endpunkte, Blockierung unautorisierter API-Ziele, Timeouts, Audit, Sensitivdatenmaskierung, Secret-Rotation.
- Nur lesende API-Requests an reale Systeme bis der Benutzer explizit die betreffenden Schreibaktionen freigibt.

## Implementierung und Parallelität
**Zuerst eine Foundation-Session:** Repository, ADRs, Datenmodell, OpenAPI-Contracts, gemeinsame Backend-Protokolle, Design-Tokens, Initialmigration, AGENTS.md, CI und Build-/Test-Skripte. Commit `foundation` und Freeze der Verträge für parallele Phase. Erst dann bis zu fünf getrennte Git-Worktrees/Branches; jeder Agent hat exklusiven Dateibesitz gemäß `docs/PARALLEL_WORKFLOW.md`. Änderungen an gemeinsamen Contracts nur über dokumentierte Vorschläge, nicht stillschweigend.

**Agent 1** Backend & Auth. **Agent 2** UI & Navigation. **Agent 3** Proxmox & Inventar. **Agent 4** Monitoring & weitere Adapter. **Agent 5** Test-/Security-Harness und Integrationsreview (erst nach Merge umfassende Integrationstests). Topologie benötigt stabile Ressourcenverträge; parallele Arbeit mit vorgegebenen Fixtures, später echte Integration.

## Release-Plan
- **R0 Foundation:** lauffähiger API-Healthcheck, Login, leerer Dashboard-Shell, DB-Migration, testbare Contracts und Systemd-Deployment-Skelett.
- **R1 Proxmox:** echte Hosts/VMs/LXC, read-only Inventar, Detailansichten; danach freigegebene Start-/Shutdown-Aktionen mit Audit.
- **R2 Topologie:** echte Beziehungen, Such-/Filterfunktionen, Quellen und Datenalter.
- **R3 Monitoring:** vorhandene Quellen, historische Dashboards und Event-Ansicht.
- **R4 Integrationen:** Pi-hole, Docker, Tailscale, TrueNAS, Home Assistant, versionsabhängig und unabhängig aktivierbar.
- **R5 Hardening:** Security-/Backup-/Restore-/Recovery-/Performance-Tests, Upgradeverfahren und produktive Freigabe.

## Definition of Done
Für jeden Meilenstein: Code und Migrationsskripte vorhanden; Format/Lint/Typecheck/Unit-/Integrationstests wirklich ausgeführt; kein Stub als fertig markiert; echte Verbindungen nur mit bereitgestellten Credentials; Fehler-/Offline-/Timeoutzustände und RBAC abgedeckt; Doku, Changelog, Betriebsanleitung aktualisiert. Status präzise kennzeichnen: `tested`, `code_only`, `blocked`, `not_started`. Vor realen Deployment- oder Schreibaktionen explizit Freigabe einholen.

## Dein erster konkreter Auftrag
Lies `AGENTS.md`, dieses Dokument, `docs/PARALLEL_WORKFLOW.md` und `docs/DEPLOYMENT_PLAYBOOK.md`. Überprüfe das Repository. Implementiere **nur R0 Foundation**, definiere eingefrorene API-Schemas und gemeinsame Ressourcenverträge, erstelle und führe Tests aus, committe auf einem Foundation-Branch. Erstelle eine Übergabedatei mit konkret verfügbaren Interfaces und noch offenen Punkten. Starte **nicht** selbst die fünf Folge-Agenten und führe **kein Deployment** auf realen Proxmox-Systemen aus, solange keine Freigabe vorliegt.
