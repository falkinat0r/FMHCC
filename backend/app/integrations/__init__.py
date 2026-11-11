"""Integrations-Implementierungen (konkrete Adapter).

Foundation besitzt: registry.py. Konkrete Adapter-Verzeichnisse
(``proxmox/``, ``monitoring/``, ``pihole/``, ...) werden von den
Folge-Agenten angelegt (siehe docs/PARALLEL_WORKFLOW.md).

Agent 4 (R1, Telemetry) bindet hier seine Adapter-Subpackages ein,
damit die ``@register``-Decoratoren bei App-Import feuern. Jeder
Import ist guarded: ein einzelner kaputter Adapter darf die App
nicht crashen (Registry bleibt dann für diesen Kind leer — ehrliche
``not_implemented``-Antworten statt Stub).
"""

import importlib

#: Agent 4, R1: Monitoring & Integrations (nur eigene Verzeichnisse).
_AGENT4_SUBPACKAGES = (
    "monitoring",
    "pihole",
    "docker",
    "tailscale",
    "truenas",
)

for _name in _AGENT4_SUBPACKAGES:
    try:
        importlib.import_module(f"app.integrations.{_name}")
    except ImportError:
        # Subpackage existiert (noch) nicht (z. B. parallel laufender
        # Agent) — bewusst still, Registry liefert not_implemented.
        pass
    except Exception:  # noqa: BLE001 - Registry-Isolation, App muss starten
        pass
