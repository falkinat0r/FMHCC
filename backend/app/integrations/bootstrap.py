"""Adapter-Registry-Bootstrap (Core, R1-Integration).

Registriert alle in diesem Build enthaltenen Adapter in der
Adapter-Registry, wenn die App gestartet wird (``create_app``).
Umsetzung des dokumentierten Vorschlags
``docs/proposals/agent3-proxmox-core-integration.md`` (Item 1):
ohne diesen Hook antworteten die Verify-Endpunkte fuer alle Adapter
ehrlich mit ``not_implemented``, weil die Registry nie vorbefuellt
wurde (R0-Verhalten, bewusst leer).

- Agent 4-Adapter (monitoring, pihole, docker, tailscale, truenas):
  registrieren sich beim Import ihrer Subpackages selbst per
  ``@register`` (guarded Package-Import in ``app.integrations``).
  Der Bootstrap registriert die Klassen ABER auch explizit:
  Import-Side-Effects feuern pro Prozess nur einmal (Import-Cache)
  und daher nicht erneut nach einem ``registry._reset_for_tests()``.
  Die explizite Registrierung macht den Bootstrap deterministisch.
- Proxmox-Adapter (Agent 3): explizite Registrierung ueber
  ``register_proxmox_adapter()`` (idempotent, kollisionsfrei —
  weicht einer Test-Fixture aus).

Kollisionsregel: ist unter einem Key bereits eine fremde Klasse
(z. B. Test-Fixture) registriert, weicht der Bootstrap davor aus —
die Registry-Kollision bleibt der Testlogik ueberlassen (entsprechend
``register_proxmox_adapter()``).

Ein kaputter Adapter-Import darf die App nicht crashen (Registry
bleibt dann fuer dieses Kind leer => ehrliche
``not_implemented``-Antworten statt Stub, docs/foundation-handoff.md).
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from app.integrations import registry

logger = logging.getLogger(__name__)

#: Agent 4, R1: in diesem Build enthaltene Adapter (Subpackage, Klasse).
#: Reihenfolge = Registrierungsreihenfolge (alphabetisch nach Kind).
_AGENT4_ADAPTERS: tuple[tuple[str, str], ...] = (
    ("app.integrations.docker", "DockerAdapter"),
    ("app.integrations.monitoring", "MonitoringAdapter"),
    ("app.integrations.pihole", "PiholeAdapter"),
    ("app.integrations.tailscale", "TailscaleAdapter"),
    ("app.integrations.truenas", "TruenasAdapter"),
)


def _register_explicit(cls: Any) -> None:
    """Trägt ``cls`` idempotent und kollisionsfrei in die Registry ein."""
    existing = registry.get_adapter(cls.kind)
    if existing is not None and existing is not cls:
        # Fremder Adapter (z. B. Test-Fixture) hat Vorrang.
        return
    registry.register(cls)


def register_all_adapters() -> None:
    """Registriert alle verfuegbaren Adapter (idempotent, nicht-abstuerzend)."""
    # Agent 4: Paket-Import feuert die guarded Subpackage-Imports und
    # damit die @register-Decoratoren (einmalig, Import-Cache).
    try:
        import app.integrations  # noqa: F401
    except Exception:  # noqa: BLE001 - Registry-Isolation, App muss starten
        logger.exception("Adapter-Import (Agent-4-Subpackages) fehlgeschlagen")

    # Agent 4: explizite Registrierung der gebündelten Adapter-Klassen —
    # deterministisch auch nach Registry-Reset, da Import-Side-Effects
    # nicht erneut feuern. Jeder Adapter isoliert: ein kaputter
    # Subpackage-Import laesst die anderen (und die App) laufen.
    for module_name, class_name in _AGENT4_ADAPTERS:
        try:
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
        except Exception:  # noqa: BLE001 - Registry-Isolation, App muss starten
            logger.exception("Adapter-Import fehlgeschlagen: %s", module_name)
            continue
        _register_explicit(cls)

    # Agent 3: explizite Registrierung (idempotent; prueft Kollision).
    try:
        from app.integrations.proxmox.adapter import register_proxmox_adapter

        register_proxmox_adapter()
    except Exception:  # noqa: BLE001 - Registry-Isolation, App muss starten
        logger.exception("Proxmox-Adapter-Registrierung fehlgeschlagen")
