"""Integrations-Tests fuer den R1-Adapter-Bootstrap (Integration/R1).

Verifiziert den Integrationsfix gemass
``docs/proposals/agent3-proxmox-core-integration.md`` (Item 1):
``create_app()`` muss die Adapter-Registry vorbefuellen, damit der
Verify-Endpunkt fuer alle in diesem Build enthaltenen Adapter
ehrlich antwortet (statt durchgaengig ``not_implemented``).
"""

from __future__ import annotations

import pytest

from app.adapters.base import BaseAdapter
from app.config import Settings
from app.integrations import registry
from app.integrations.bootstrap import register_all_adapters
from app.integrations.proxmox.adapter import ProxmoxAdapter
from app.main import create_app
from app.models.integrations import AdapterKind

_ALL_BUILTIN_KINDS = ("proxmox", "monitoring", "pihole", "docker", "tailscale", "truenas")


class _FixtureAdapter(BaseAdapter):
    """Test-Doppel (klar gekennzeichnet): belegt die Kollisionsregel."""

    kind = AdapterKind.PROXMOX


@pytest.fixture(autouse=True)
def _registry():
    registry._reset_for_tests()
    yield
    registry._reset_for_tests()


def test_register_all_adapters_registers_every_builtin_adapter() -> None:
    register_all_adapters()
    assert registry.get_adapter("proxmox") is ProxmoxAdapter
    for kind in _ALL_BUILTIN_KINDS:
        assert kind in registry.available_adapters(), kind


def test_register_all_adapters_is_idempotent() -> None:
    register_all_adapters()
    register_all_adapters()  # darf nicht werfen (zweiter App-Start/Reload)
    assert registry.get_adapter("proxmox") is ProxmoxAdapter


def test_create_app_populates_registry() -> None:
    settings = Settings(
        environment="development",
        database_url="sqlite://",
        bootstrap_token="bootstrap-hook-test-0123456789abcdef",
        git_commit="bootstrap-test",
    )
    create_app(settings)
    assert registry.get_adapter("proxmox") is ProxmoxAdapter
    assert "monitoring" in registry.available_adapters()


def test_register_all_adapters_never_overrides_test_fixture() -> None:
    """R0-Testbasis (FakeAdapter, kind=proxmox) muss ueberschreibbar bleiben:
    die Registrierung weicht einem bereits eingetragenen, fremden
    Proxmox-Adapter aus (keine Registry-Kollision in Tests)."""
    registry.register(_FixtureAdapter)
    register_all_adapters()
    assert registry.get_adapter("proxmox") is _FixtureAdapter
