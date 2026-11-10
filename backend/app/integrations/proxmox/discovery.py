"""Proxmox-Discovery (Agent 3, R1): Nodes, VMs, LXC, Zusatzstatus.

Nur lesende GET-Requests. Standalone und Cluster werden unterstuetzt
(Cluster-Mitgliedschaft ueber ``/cluster``, Quorum ueber ``/cluster/health``).

Fehlerstrategie (bewusst zweistufig):
- Fundamentale Leseoperationen (``/nodes``) duerfen NICHT degradieren —
  Netzwerk-/Auth-/Antwortfehler brechen die Discovery mit AdapterError ab.
- Optionalen Details (Node-Status, Storage, Tasks, VM-/LXC-Config,
  Snapshots, Cluster-Health) degradieren pro Ressource auf ``None``;
  ein fehlrechteter oder offline-Node blockiert den Rest nicht.
- Offline-Node (``status == "offline"`` in der /nodes-Liste): es werden
  KEINE weiteren Requests an den Node versendet (er antwortet ohnehin
  nicht); die Resource wird ehrlich mit ``down`` gemeldet.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

from app.adapters.base import AdapterCapabilities, AdapterState, AdapterStatus, ResourceRecord
from app.adapters.errors import AdapterApiError, AdapterVersionError
from app.integrations.proxmox import normalize
from app.integrations.proxmox.client import ProxmoxClient
from app.integrations.proxmox.config import MINIMUM_PVE_MAJOR
from app.models.mixins import utcnow

_VERSION_RE = re.compile(r"^(\d+)\.")


def extract_version(data: Any) -> str | None:
    """'version' (oder 'release') aus der /version-Antwort; sonst None."""
    if not isinstance(data, dict):
        return None
    for key in ("version", "release"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def major_version(version: str | None) -> int | None:
    if version is None:
        return None
    match = _VERSION_RE.match(version.strip())
    return int(match.group(1)) if match else None


class ProxmoxDiscovery:
    """Orchestriert alle lesenden Proxmox-Abfragen fuer eine Integration."""

    def __init__(self, client: ProxmoxClient, *, fetch_details: bool = True) -> None:
        self._client = client
        self._fetch_details = fetch_details

    # ------------------------------------------------------------------ verify

    async def verify(self) -> AdapterStatus:
        """Verbindung + Token + Versionsgate (nur lesende Requests).

        1. GET /version  → TLS/Erreichbarkeit, Versionscheck (min. PVE 8)
        2. GET /nodes    → Token-Validitaet + Grundrechte (401/403 → Fehler)
        """
        version_data = await self._client.get("/version")
        pve_version = extract_version(version_data)
        major = major_version(pve_version)
        if major is not None and major < MINIMUM_PVE_MAJOR:
            raise AdapterVersionError(
                f"Proxmox VE {pve_version} wird nicht unterstuetzt (Minimum: {MINIMUM_PVE_MAJOR}.x)"
            )
        await self._client.get("/nodes")
        return AdapterStatus(
            state=AdapterState.OK,
            message="Proxmox-API erreichbar, API-Token gueltig",
            api_version=pve_version,
            checked_at=utcnow(),
        )

    # ----------------------------------------------------------- capabilities

    async def capabilities(self) -> AdapterCapabilities:
        pve_version = extract_version(await self._client.get_optional("/version"))
        cluster = await self._client.get_optional("/cluster")
        cluster_nodes = (
            [str(item.get("id")) for item in cluster if isinstance(item, dict) and item.get("id")]
            if isinstance(cluster, list)
            else []
        )
        if isinstance(cluster, list) and len(cluster_nodes) > 1:
            cluster_mode = "cluster"
        elif isinstance(cluster, list) and len(cluster_nodes) == 0:
            cluster_mode = "standalone"
        else:
            cluster_mode = "unknown"

        health = await self._client.get_optional("/cluster/health")
        return AdapterCapabilities(
            features=["discover", "health", "act:start", "act:shutdown", "act:reboot"],
            api_version=pve_version,
            extra={
                "cluster_mode": cluster_mode,
                "cluster_members": cluster_nodes or None,
                "quorum": normalize.quorum_ok_from(health),
                "min_pve_version": f"{MINIMUM_PVE_MAJOR}.x",
            },
        )

    # --------------------------------------------------------------- discover

    async def discover(self) -> AsyncIterator[ResourceRecord]:
        """Nodes (zuerst, als Parents), dann VMs/LXC pro Node."""
        observed_at = utcnow()

        nodes_raw = await self._client.get("/nodes")
        if not isinstance(nodes_raw, list):
            raise AdapterApiError("Fehlerhafte API-Antwort: /nodes liefert keine Liste", http_status=200)
        nodes = [item for item in nodes_raw if isinstance(item, dict) and item.get("id")]

        # Cluster-Mitgliedschaft (option): offline-Nodes stehen hier auch
        # noch, selbst wenn sie in /nodes als offline gekennzeichnet sind.
        # None = Endpunkt nicht ermittelbar (Rechte/Fehler); [] = Standalone.
        cluster = await self._client.get_optional("/cluster")
        cluster_names: list[str] | None = None
        if isinstance(cluster, list):
            cluster_names = [str(item.get("id")) for item in cluster if isinstance(item, dict) and item.get("id")]
        health = await self._client.get_optional("/cluster/health")
        cluster_health: dict | None = health if isinstance(health, dict) else None

        for node in nodes:
            name = str(node.get("id"))
            raw_status = node.get("status")
            reachable = not (isinstance(raw_status, str) and raw_status.strip().lower() == "offline")

            detail = status = storages = tasks = None
            if reachable:
                detail = await self._client.get_optional(f"/nodes/{name}")
                status = await self._client.get_optional(f"/nodes/{name}/status")
                storages = await self._client.get_optional(f"/nodes/{name}/storage")
                tasks = await self._client.get_optional(f"/nodes/{name}/tasks")

            yield normalize.node_record(
                node,
                detail if isinstance(detail, dict) else None,
                status if isinstance(status, dict) else None,
                storages if isinstance(storages, list) else None,
                tasks if isinstance(tasks, list) else None,
                cluster_health,
                cluster_node_names=cluster_names,
                observed_at=observed_at,
            )

            if not reachable:
                continue

            vms = await self._client.get_optional(f"/nodes/{name}/qemu")
            for entry in vms if isinstance(vms, list) else []:
                if not isinstance(entry, dict) or entry.get("vmid") is None:
                    continue
                vmid = str(entry["vmid"])
                config, snapshots = None, None
                if self._fetch_details:
                    config = await self._client.get_optional(f"/nodes/{name}/qemu/{vmid}/config")
                    snapshots = await self._client.get_optional(f"/nodes/{name}/qemu/{vmid}/snapshot")
                yield normalize.vm_record(
                    entry,
                    config if isinstance(config, dict) else None,
                    snapshots if isinstance(snapshots, list) else None,
                    node=name,
                    observed_at=observed_at,
                )

            containers = await self._client.get_optional(f"/nodes/{name}/containers")
            for entry in containers if isinstance(containers, list) else []:
                if not isinstance(entry, dict) or entry.get("cid") is None:
                    continue
                cid = str(entry["cid"])
                config, snapshots = None, None
                if self._fetch_details:
                    config = await self._client.get_optional(f"/nodes/{name}/containers/{cid}/config")
                    # LXC-Snapshots liegen unter /lxc/{cid}/snapshot
                    snapshots = await self._client.get_optional(f"/nodes/{name}/lxc/{cid}/snapshot")
                yield normalize.lxc_record(
                    entry,
                    config if isinstance(config, dict) else None,
                    snapshots if isinstance(snapshots, list) else None,
                    node=name,
                    observed_at=observed_at,
                )
