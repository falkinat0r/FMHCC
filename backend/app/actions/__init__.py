"""ActionJob-Domainservice (R1, Agent 1: Backend Core & Security).

Idempotenzbewusste, auditierte Schreibanfuege fuer Infrastrukturen
(action_jobs, Schema R0-frozen). Dieser Modul liefert NUR die
serverseitige Dienstlogik (Erstellung, Statusuebergänge, RBAC, Audit).

Die eigentlichen (API-)Endpunkte und die Adapter-Ausfuehrung gehoeren zu
Agent 3 (Proxmox) bzw. zu spaeteren Releases; bis dahin ist die
Tabelle bewusst nicht ueber die API schreibbar (keine Endpunkte im
eingefrorenen R0-Routenplan). Keine direkte Ausfuehrung echter
Infrastrukturaktionen.
"""
