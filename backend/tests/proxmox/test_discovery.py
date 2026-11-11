"""Discovery-Tests (Agent 3, R1): verify, capabilities, discover.

Szenarien: Standalone, Multi-Node-Cluster, Offline-Node, Version-Gate,
fehlendes Quorum, fehlende Details (Rechte), fundamentale Abbrueche,
Details-Skip via Option.
"""

from __future__ import annotations

import pytest

from app.adapters.base import AdapterState
from app.adapters.errors import (
    AdapterApiError,
    AdapterAuthError,
    AdapterUnreachableError,
    AdapterVersionError,
)
from app.integrations.proxmox.client import ProxmoxClient
from app.integrations.proxmox.discovery import ProxmoxDiscovery, extract_version, major_version
from app.models.resources import ResourceStatus, ResourceType
from tests.proxmox.conftest import client_request, discover_records, run
from tests.proxmox.fixtures import cluster_scenario, standalone_scenario


def _verify(server, **extra):
    async def _fn(client: ProxmoxClient):
        return await ProxmoxDiscovery(client, fetch_details=False).verify()

    return client_request(server, _fn, **extra)


# --------------------------------------------------------------------- helpers


def test_extract_version_and_major() -> None:
    assert extract_version({"version": "9.1.2"}) == "9.1.2"
    assert extract_version({"release": "8.2.4"}) == "8.2.4"
    assert extract_version({}) is None
    assert extract_version("nichts") is None
    assert major_version("9.1.2") == 9
    assert major_version("7.4.1") == 7
    assert major_version(None) is None
    assert major_version("unparsbar") is None


# ---------------------------------------------------------------------- verify


def test_verify_standalone_ok() -> None:
    server = standalone_scenario()
    status = _verify(server)
    assert status.state is AdapterState.OK
    assert status.api_version == "9.1.2"
    assert status.checked_at is not None
    # Genauer Request-Verlauf: zuerst /version (Gate), dann /nodes (Token)
    assert server.paths()[:2] == ["/version", "/nodes"]


def test_verify_cluster_ok() -> None:
    status = _verify(cluster_scenario())
    assert status.state is AdapterState.OK
    assert status.api_version == "9.1.2"


def test_verify_invalid_token_fails_with_auth_error() -> None:
    server = standalone_scenario()

    async def _fn(client: ProxmoxClient):
        client._http.headers["Authorization"] = "PVEAPIToken=wrong@pve!token=00000000000000000000000000000000"
        return await ProxmoxDiscovery(client, fetch_details=False).verify()

    with pytest.raises(AdapterAuthError) as exc_info:
        client_request(server, _fn)
    assert exc_info.value.state is AdapterState.AUTH_FAILED


def test_verify_version_gate_rejects_pve7() -> None:
    server = standalone_scenario(version="7.4.1")
    with pytest.raises(AdapterVersionError) as exc_info:
        _verify(server)
    assert exc_info.value.state is AdapterState.VERSION_UNSUPPORTED
    assert "8.x" in exc_info.value.message
    # Das Gate bricht VOR der Node-Anfrage ab
    assert "/nodes" not in server.paths()


def test_verify_unreachable_aborts() -> None:
    server = standalone_scenario()
    server.network_error = "unreachable"
    with pytest.raises(AdapterUnreachableError) as exc_info:
        _verify(server)
    assert exc_info.value.state is AdapterState.UNREACHABLE


def test_discover_nodes_must_be_list() -> None:
    """Fehlerhafte /nodes-Antwort (kein List) bricht die Discovery ab."""
    server = standalone_scenario()
    server.nodes = "keine-liste"  # fehlerhafte Envelope-Data
    with pytest.raises(AdapterApiError) as exc_info:
        discover_records(server)
    assert "Liste" in exc_info.value.message


# ------------------------------------------------------------------ capabilities


def test_capabilities_standalone() -> None:
    server = standalone_scenario()

    async def _fn(client: ProxmoxClient):
        return await ProxmoxDiscovery(client).capabilities()

    caps = client_request(server, _fn)
    assert set(caps.features) >= {"discover", "health", "act:start", "act:shutdown", "act:reboot"}
    assert caps.api_version == "9.1.2"
    assert caps.extra["cluster_mode"] == "standalone"
    assert caps.extra["quorum"] is None
    assert caps.extra["min_pve_version"] == "8.x"


def test_capabilities_cluster_with_quorum() -> None:
    server = cluster_scenario()

    async def _fn(client: ProxmoxClient):
        return await ProxmoxDiscovery(client).capabilities()

    caps = client_request(server, _fn)
    assert caps.extra["cluster_mode"] == "cluster"
    assert caps.extra["cluster_members"] == ["pve1", "pve2", "pve3"]
    assert caps.extra["quorum"] is True


def test_capabilities_cluster_without_quorum() -> None:
    server = cluster_scenario(quorum_ok=0)

    async def _fn(client: ProxmoxClient):
        return await ProxmoxDiscovery(client).capabilities()

    caps = client_request(server, _fn)
    assert caps.extra["quorum"] is False


# -------------------------------------------------------------------- discover


def _by_key(records, resource_type: ResourceType, external_id: str):
    return next(r for r in records if r.resource_type is resource_type and r.external_id == external_id)


def test_discover_standalone_full_inventory() -> None:
    server = standalone_scenario()
    records = discover_records(server)

    # Reihung: Node zuerst (Parents), dann VMs, dann LXC
    assert [r.external_id for r in records] == ["pve1", "101", "102", "103", "201", "202"]
    assert records[0].resource_type is ResourceType.NODE

    node = records[0]
    assert node.status is ResourceStatus.HEALTHY
    assert node.payload["pve_version"] == "9.1.2"
    assert node.payload["cpu_count"] == 8
    assert node.payload["memory_total_bytes"] == 34359738368
    assert node.payload["memory_used_bytes"] == 21474836480
    assert node.payload["ip_addresses"][0]["address"] == "10.0.0.2"
    assert node.payload["storages"][0]["id"] == "local"
    # Cluster-Evidenz: Standalone => is_cluster=false (nicht None!)
    assert node.payload["cluster"]["is_cluster"] is False
    assert node.payload["cluster"]["members"] == []

    vm101 = _by_key(records, ResourceType.VM, "101")
    assert vm101.status is ResourceStatus.HEALTHY  # running
    assert vm101.parent_external_id == "pve1"
    assert vm101.parent_resource_type is ResourceType.NODE
    assert vm101.relation_type == "runs_on"
    assert vm101.payload["node"] == "pve1"
    assert vm101.payload["memory_total_bytes"] == 4294967296
    assert vm101.payload["cpu_cores_configured"] == 4
    disks = {disk["device"]: disk for disk in vm101.payload["disks"]}
    assert set(disks) == {"scsi0", "ide2"}
    assert disks["scsi0"]["size_bytes"] == 32 * 1024**3
    assert disks["scsi0"]["storage"] == "local-lvm"
    assert disks["scsi0"]["cache"] == "writeback"
    assert disks["ide2"]["media"] == "cdrom"
    assert vm101.payload["network"][0]["bridge"] == "vmbr0"
    assert vm101.payload["snapshots"] == ["pre-upgrade", "snap-2026-11-01"]

    assert _by_key(records, ResourceType.VM, "102").status is ResourceStatus.DOWN  # stopped
    assert _by_key(records, ResourceType.VM, "103").status is ResourceStatus.DEGRADED  # paused

    lxc201 = _by_key(records, ResourceType.LXC, "201")
    assert lxc201.status is ResourceStatus.HEALTHY
    assert lxc201.payload["hostname"] == "phole"
    assert lxc201.payload["memory_total_bytes"] == 2147483648
    assert lxc201.payload["network"][0]["ip"] == "10.0.0.31/24"
    assert lxc201.payload["snapshots"] == ["before-migration"]
    assert _by_key(records, ResourceType.LXC, "202").status is ResourceStatus.DOWN  # stopped

    # observed_at ist ueber alle Records identisch (ein Discover-Durchlauf)
    assert len({r.observed_at for r in records}) == 1


def test_discover_cluster_with_offline_node() -> None:
    server = cluster_scenario()
    records = discover_records(server)

    assert [r.external_id for r in records if r.resource_type is ResourceType.NODE] == ["pve1", "pve2", "pve3"]
    assert _by_key(records, ResourceType.NODE, "pve1").status is ResourceStatus.HEALTHY
    assert _by_key(records, ResourceType.NODE, "pve2").status is ResourceStatus.HEALTHY
    assert _by_key(records, ResourceType.NODE, "pve3").status is ResourceStatus.DOWN

    # Offline-Node: KEINE Node-spezifischen Requests (er antwortet nicht)
    offline_paths = [p for p in server.paths() if p.startswith("/nodes/pve3")]
    assert offline_paths == []

    # VM auf pve2 wird entdeckt, VMs auf pve1 bleiben erhalten
    vm104 = _by_key(records, ResourceType.VM, "104")
    assert vm104.status is ResourceStatus.HEALTHY
    assert vm104.payload["node"] == "pve2"
    assert _by_key(records, ResourceType.VM, "101").payload["node"] == "pve1"

    # Cluster-Evidenz im Node-Payload
    node = _by_key(records, ResourceType.NODE, "pve1")
    assert node.payload["cluster"]["is_cluster"] is True
    assert node.payload["cluster"]["members"] == ["pve1", "pve2", "pve3"]
    assert node.payload["cluster"]["quorum_ok"] == 1


def test_discover_missing_quorum_degrades_online_nodes() -> None:
    server = cluster_scenario(quorum_ok=0)
    records = discover_records(server)

    for node_name in ("pve1", "pve2"):
        node = _by_key(records, ResourceType.NODE, node_name)
        assert node.status is ResourceStatus.DEGRADED, node_name
        assert "Quorum" in (node.payload["note"] or "")
    # Offline-Node bleibt down (Quorum ist zweitrangig)
    assert _by_key(records, ResourceType.NODE, "pve3").status is ResourceStatus.DOWN
    # Compute-Ressourcen werden dennoch ehrlich berichtet
    assert _by_key(records, ResourceType.VM, "101").status is ResourceStatus.HEALTHY


def test_discover_degrades_on_missing_details_permissions() -> None:
    server = standalone_scenario()
    server.forbidden_paths = {
        "/nodes/pve1",
        "/nodes/pve1/status",
        "/nodes/pve1/storage",
        "/nodes/pve1/tasks",
    }
    records = discover_records(server)

    # Discovery bricht NICHT ab — alle 6 Resources existieren
    assert len(records) == 6
    node = records[0]
    assert node.status is ResourceStatus.HEALTHY  # aus der /nodes-Liste
    # Fehlende Details bleiben None — nichts wird erfunden
    assert node.payload["memory_total_bytes"] is None
    assert node.payload["storages"] is None
    assert node.payload["tasks"] is None
    # VM-/LXC-Lists und -Details bleiben verfuegbar
    assert _by_key(records, ResourceType.VM, "101").payload["disks"] is not None


def test_discover_aborts_on_unreachable_nodes() -> None:
    server = standalone_scenario()
    server.network_error = "unreachable"
    with pytest.raises(AdapterUnreachableError):
        discover_records(server)


def test_discover_aborts_on_forbidden_nodes() -> None:
    server = standalone_scenario()
    server.forbidden_paths = {"/nodes"}
    with pytest.raises(AdapterAuthError) as exc_info:
        discover_records(server)
    assert exc_info.value.state is AdapterState.AUTH_FAILED


def test_discover_malformed_nodes_response_aborts() -> None:
    server = standalone_scenario()
    server.malformed_paths = {"/nodes"}
    with pytest.raises(AdapterApiError):
        discover_records(server)


def test_discover_skips_details_when_disabled() -> None:
    server = standalone_scenario()
    records = discover_records(server, fetch_resource_details="false")

    assert len(records) == 6
    # Keine Config-/Snapshot-Requests
    detail_paths = [p for p in server.paths() if "/config" in p or "/snapshot" in p]
    assert detail_paths == []
    # Grunddaten kommen aus den Listen (maxmem/MaxMemory statt Config-MB)
    vm101 = _by_key(records, ResourceType.VM, "101")
    assert vm101.payload["memory_total_bytes"] == 4294967296
    assert vm101.payload["disks"] is None
    assert vm101.payload["snapshots"] is None

    lxc201 = _by_key(records, ResourceType.LXC, "201")
    assert lxc201.payload["memory_total_bytes"] == 2147483648
    assert lxc201.payload["rootfs"] is None


def test_discover_uses_cluster_health_none_gracefully() -> None:
    """Kein Cluster-Health (404) + Standalone: Discovery bleibt intakt."""
    server = standalone_scenario()
    server.cluster = None  # /cluster liefert 404
    server.cluster_health = None
    records = discover_records(server)
    assert len(records) == 6
    node = records[0]
    # Ohne jede Cluster-Datenquelle: Payload None (kein erfundener Wert)
    assert node.payload["cluster"] is None
    assert node.status is ResourceStatus.HEALTHY


# ------------------------------------------------------------------- run wrapper


def test_run_helper_executes_async() -> None:
    async def _noop() -> str:
        return "ok"

    assert run(_noop()) == "ok"
