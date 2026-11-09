# Agent 3 — Proxmox & Infrastruktur-Inventar

Lies globale Regeln. Bearbeite Proxmox-Adapter/-Inventar und eigene Tests.

- Prüfe Proxmox REST API und auth scopes gegen vorhandene Version; API token mit minimalen Rechten.
- Node-/VM-/LXC-Discovery, Standalone und Cluster, API-Tasks, Status/CPU/RAM/Storage; Normalisierung nach Foundation-Contracts.
- Resilienz: 401/403, 404, Rate Limit, Timeout, Zertifikatsvalidierung, Teilfehler, Cluster ohne Quorum, Host offline.
- Resource-Key mit integration_id/resource_type/external_id und observed_at; Beziehungen Host→VM/LXC mit Evidence=api.
- Read-only zuerst. Start/Shutdown/Reboot erst nach vorhandener RBAC-/Audit-/ActionJob-Schnittstelle; reale Schreibtests nur an autorisierter Test-VM und mit Freigabe.
- Fake-API-Server/Fixtures und Contract-Tests.

Abnahme: reproduzierbare Testabdeckung, dokumentierte API-Rechte, keine produktive Mutation ohne Freigabe.
