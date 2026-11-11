"""Pi-hole-Integration (Agent 4, R1).

Adapter für Pi-hole-Instanzen (v5 api.php und v6 REST); mehrere Instanzen
als mehrere Integrationen.
"""

from app.integrations.pihole.adapter import PiholeAdapter, PiholeApiGeneration

__all__ = ["PiholeAdapter", "PiholeApiGeneration"]
