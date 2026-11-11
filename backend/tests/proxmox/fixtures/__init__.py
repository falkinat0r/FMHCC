"""Test-Fixtures fuer den Proxmox-Adapter (Agent 3, R1)."""

from tests.proxmox.fixtures.server import (
    VALID_TOKEN_HEADER,
    FakeProxmoxServer,
    cluster_scenario,
    make_upid,
    standalone_scenario,
)

__all__ = [
    "VALID_TOKEN_HEADER",
    "FakeProxmoxServer",
    "cluster_scenario",
    "make_upid",
    "standalone_scenario",
]
