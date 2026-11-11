"""Registry-Wiring-Tests (Agent 4, R1): App-Import registriert Adapter.

Die guarded Imports in app/integrations/__init__.py muessen die
Agent-4-Adapter (monitoring, pihole, docker, tailscale, truenas) in
der Registry eintragen, ohne dass der Rest der App davon abhaengt.
"""

from __future__ import annotations

import importlib

from app.integrations import registry
from app.integrations.docker.adapter import DockerAdapter
from app.integrations.monitoring.engine import MonitoringAdapter
from app.integrations.pihole.adapter import PiholeAdapter
from app.integrations.tailscale.adapter import TailscaleAdapter
from app.integrations.truenas.adapter import TruenasAdapter


def test_agent4_adapters_are_registered() -> None:
    # Import erneut anstossen (idempotent), falls noch nicht geschehen
    importlib.import_module("app.integrations")
    assert registry.get_adapter("monitoring") is MonitoringAdapter
    assert registry.get_adapter("pihole") is PiholeAdapter
    assert registry.get_adapter("docker") is DockerAdapter
    assert registry.get_adapter("tailscale") is TailscaleAdapter
    assert registry.get_adapter("truenas") is TruenasAdapter
    available = registry.available_adapters()
    for kind in ("monitoring", "pihole", "docker", "tailscale", "truenas"):
        assert kind in available


def test_registered_adapters_are_instantiable_noarg() -> None:
    """Der Verify-Endpoint ruft adapter_cls() ohne Argumente auf.

    Alle Agent-4-Adapter muessen daher ohne Argumente instantiiert
    werden koennen (Test-Transport kommt ueber den optionalen
    Konstruktor-Parameter, nicht ueber die Signatur-Pflicht).
    """
    for cls in (MonitoringAdapter, PiholeAdapter, DockerAdapter, TailscaleAdapter, TruenasAdapter):
        instance = cls()
        assert instance is not None
