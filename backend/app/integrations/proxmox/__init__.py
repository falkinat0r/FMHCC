"""Proxmox-VE-Integration (Agent 3, R1).

Implementiert das frozen ``IntegrationAdapter``-Protokoll fuer Proxmox VE
(Standalone und Cluster):

- ``client.py``      API-Client (Token-Auth, TLS-Verifizierung, Timeouts,
                     Retry nur fuer GET, Rate-Limiting, Fehlermauerung)
- ``config.py``      Token-Parsing und Adapter-Optionen (aus AdapterConfig.extra)
- ``discovery.py``   Node-/VM-/LXC-Discovery inkl. Zusatzstatus
- ``normalize.py``   Normalisierung in ResourceRecords (Status-Mapping, Payloads)
- ``adapter.py``     ``ProxmoxAdapter`` (verify/capabilities/discover/health/act)
- ``actions.py``     ActionJob-Orchestrierung (RBAC + Audit + Adapter-Call)

Registrierung: Der Adapter registriert sich NICHT automatisch beim Import —
die App muss ``register_proxmox_adapter()`` aufrufen (siehe
``docs/agent-reports/R1-proxmox.md``, Abschnitt "Core-Verbindungs-
anforderung"). So bleibt die R0-Testbasis (FakeAdapter-Registry-Tests)
unberuehrt.
"""

from app.integrations.proxmox.adapter import ProxmoxAdapter, register_proxmox_adapter

__all__ = ["ProxmoxAdapter", "register_proxmox_adapter"]
