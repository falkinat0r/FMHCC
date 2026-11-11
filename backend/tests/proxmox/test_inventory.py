"""Inventar-Sync-Tests (Agent 3, R1).

Verifiziert den einzigen Inventar-Schreibweg (upsert_resources) mit
Proxmox-Discover-Daten: Deduplizierung, Relationships, ehrliche
Statuswerte, Idempotenz (zweiter Durchlauf erzeugt keine Duplikate).
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.inventory.proxmox import SyncResult, sync_proxmox_inventory
from app.models.integrations import AdapterKind
from app.models.resources import (
    Resource,
    ResourceRelation,
    ResourceSource,
    ResourceStatus,
    ResourceType,
)
from tests.proxmox.conftest import discover_records, make_integration
from tests.proxmox.fixtures import cluster_scenario, standalone_scenario


def _resource_count(db, resource_type: ResourceType | None = None) -> int:
    query = select(func.count()).select_from(Resource)
    if resource_type is not None:
        query = query.where(Resource.resource_type == resource_type)
    return db.scalar(query) or 0


def _resource(db, resource_type: ResourceType, external_id: str) -> Resource:
    return db.scalar(
        select(Resource).where(Resource.resource_type == resource_type, Resource.external_id == external_id)
    )


def test_sync_standalone_creates_resources_and_relations(db) -> None:
    integration = make_integration(db)
    records = discover_records(standalone_scenario())
    assert len(records) == 6

    result: SyncResult = sync_proxmox_inventory(db, integration=integration, records=records)
    assert (result.total, result.created, result.updated, result.relations_created) == (6, 6, 0, 5)

    assert _resource_count(db) == 6
    assert _resource_count(db, ResourceType.NODE) == 1
    assert _resource_count(db, ResourceType.VM) == 3
    assert _resource_count(db, ResourceType.LXC) == 2
    assert db.scalar(select(func.count()).select_from(ResourceRelation)) == 5

    node = _resource(db, ResourceType.NODE, "pve1")
    assert node is not None
    assert node.status is ResourceStatus.HEALTHY
    assert node.source is ResourceSource.API
    assert node.payload["pve_version"] == "9.1.2"
    assert node.first_seen_at == node.last_seen_at == node.observed_at

    vm101 = _resource(db, ResourceType.VM, "101")
    assert vm101 is not None
    assert vm101.status is ResourceStatus.HEALTHY
    disks = {disk["device"]: disk for disk in vm101.payload["disks"]}
    assert disks["scsi0"]["size_bytes"] == 32 * 1024**3


def test_sync_is_idempotent_on_second_run(db) -> None:
    integration = make_integration(db)
    first = sync_proxmox_inventory(db, integration=integration, records=discover_records(standalone_scenario()))
    assert (first.created, first.updated, first.relations_created) == (6, 0, 5)

    second = sync_proxmox_inventory(db, integration=integration, records=discover_records(standalone_scenario()))
    assert (second.created, second.updated, second.relations_created) == (0, 6, 0)

    # Keine Duplikate, keine doppelten Beziehungen
    assert _resource_count(db) == 6
    assert db.scalar(select(func.count()).select_from(ResourceRelation)) == 5


def test_sync_updates_status_and_observed_at(db) -> None:
    integration = make_integration(db)
    server = standalone_scenario()
    first = discover_records(server)
    sync_proxmox_inventory(db, integration=integration, records=first)

    # VM 101 wird gestoppt => Status aendert sich beim naechen Sync
    server.qemu["pve1"][0]["status"] = "stopped"
    second = discover_records(server)
    result = sync_proxmox_inventory(db, integration=integration, records=second)
    assert result.updated == 6
    assert result.created == 0

    vm101 = _resource(db, ResourceType.VM, "101")
    assert vm101 is not None
    assert vm101.status is ResourceStatus.DOWN
    assert vm101.first_seen_at < vm101.last_seen_at


def test_sync_cluster_offline_node_is_down(db) -> None:
    integration = make_integration(db)
    records = discover_records(cluster_scenario())

    sync_proxmox_inventory(db, integration=integration, records=records)

    pve1 = _resource(db, ResourceType.NODE, "pve1")
    pve2 = _resource(db, ResourceType.NODE, "pve2")
    pve3 = _resource(db, ResourceType.NODE, "pve3")
    vm104 = _resource(db, ResourceType.VM, "104")
    assert all(x is not None for x in (pve1, pve2, pve3, vm104))
    assert pve1.status is ResourceStatus.HEALTHY
    assert pve2.status is ResourceStatus.HEALTHY
    assert pve3.status is ResourceStatus.DOWN
    assert vm104.status is ResourceStatus.HEALTHY

    # Beziehungen: 5 Kinder auf pve1 + VM 104 auf pve2
    relations = db.scalars(select(ResourceRelation)).all()
    assert {(r.relation_type, r.evidence) for r in relations} == {("runs_on", ResourceSource.API)}
    assert len(relations) == 6


def test_sync_missing_details_are_not_fabricated(db) -> None:
    integration = make_integration(db)
    server = standalone_scenario()
    server.forbidden_paths = {"/nodes/pve1/status", "/nodes/pve1/storage"}
    records = discover_records(server)

    result = sync_proxmox_inventory(db, integration=integration, records=records)
    assert result.created == 6

    node = _resource(db, ResourceType.NODE, "pve1")
    assert node is not None
    # Fehlende Details => None im Payload (kein erfundener Wert)
    assert node.payload["memory_used_bytes"] is None
    assert node.payload["storages"] is None
    assert node.payload["cpu_usage"] is None


def test_sync_does_not_write_for_other_integrations(db) -> None:
    integration_a = make_integration(db, integration_id="pve-a")
    integration_b = make_integration(db, integration_id="pve-b")

    sync_proxmox_inventory(db, integration=integration_a, records=discover_records(standalone_scenario()))
    sync_proxmox_inventory(db, integration=integration_b, records=discover_records(standalone_scenario()))

    # Gleiche external_ids, aber pro Integration dedupliziert
    assert _resource_count(db) == 12
    assert (
        db.scalar(select(func.count()).select_from(Resource).where(Resource.integration_id == integration_a.id))
        == 6
    )
    assert integration_b.adapter is AdapterKind.PROXMOX
