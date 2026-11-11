"""Normalisierung der Proxmox-API-Daten in frozen ResourceRecords (Agent 3, R1).

Alle Funktionen sind rein (keine I/O) und arbeiten nur mit echten
Proxmox-API-Antworten. Fehlende Felder bleiben ``None`` — es werden
niemals Werte erfunden. Die Status-Mappings sind in der Doku
(``docs/agent-reports/R1-proxmox.md``) als Entscheide festgehalten.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.adapters.base import ResourceRecord
from app.models.resources import ResourceStatus, ResourceType

_SIZE_SUFFIXES = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}

_VM_DISK_RE = re.compile(r"^(scsi|ide|sata)\d+$")
_NET_RE = re.compile(r"^net\d+$")


# --------------------------------------------------------------------- helpers

def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def parse_pve_size(value: Any) -> int | None:
    """PVE-Grössenangabe in Bytes.

    '32G' / '4096M' / '1T' (Suffix-K/Z) werden geparst; ints/floats
    werden als bereits in Bytes (oder im Kontext KB — aufruferseitig
    dokumentiert) übernommen; alles andere → None.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        multiplier = 1
        if text[-1].upper() in _SIZE_SUFFIXES:
            multiplier = _SIZE_SUFFIXES[text[-1].upper()]
            text = text[:-1]
        try:
            return int(float(text) * multiplier)
        except ValueError:
            return None
    return None


def mb_to_bytes(value: Any) -> int | None:
    """MB-Wert (Proxmox-Config 'memory'/'swap' sind MB) in Bytes."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value * 1024 * 1024)
    if isinstance(value, str):
        try:
            return int(float(value.strip()) * 1024 * 1024)
        except ValueError:
            return None
    return None


def map_compute_status(raw: Any) -> ResourceStatus:
    """VM/LXC-Status (running/paused/stopped) auf das HCC-Fuenf-Modell.

    - running  → healthy  (laeuft, keine Fehler bekannt)
    - paused   → degraded
    - stopped  → down     (nicht laeuft — ehrlich, kein Erfolgswert)
    - sonst    → unknown
    """
    if not isinstance(raw, str):
        return ResourceStatus.UNKNOWN
    value = raw.strip().lower()
    if value == "running":
        return ResourceStatus.HEALTHY
    if value == "paused":
        return ResourceStatus.DEGRADED
    if value == "stopped":
        return ResourceStatus.DOWN
    return ResourceStatus.UNKNOWN


def map_node_status(raw: Any, *, quorum_ok: bool | None) -> tuple[ResourceStatus, str | None]:
    """Node-Status mappen; fehlendes Cluster-Quorum degradiert einen Node.

    Liefert ``(status, note)``.
    """
    if not isinstance(raw, str):
        return ResourceStatus.UNKNOWN, "Node-Status nicht ermittelbar"
    value = raw.strip().lower()
    if value == "offline":
        return ResourceStatus.DOWN, None
    if value == "maintenance":
        return ResourceStatus.DEGRADED, "Node im Wartungsmodus"
    if value == "online":
        if quorum_ok is False:
            return ResourceStatus.DEGRADED, "Cluster ohne Quorum (keine Schreib-Quorum)"
        return ResourceStatus.HEALTHY, None
    return ResourceStatus.UNKNOWN, f"unbekannter Node-Status: {value}"


def quorum_ok_from(health: dict) -> bool | None:
    """Quorum-Auswertung aus ``/cluster/health`` (None = nicht ermittelbar)."""
    if not health:
        return None
    value = health.get("quorum_ok")
    if value is not None and not isinstance(value, bool):
        return bool(value)
    if value is not None:
        return value
    quorum, total = health.get("quorum"), health.get("total")
    if isinstance(quorum, (int, float)) and isinstance(total, (int, float)) and total > 0:
        return quorum > total / 2
    return None


# --------------------------------------------------------------------- payloads

def _storage_payloads(storages: list | None) -> list[dict[str, Any]] | None:
    if storages is None:
        return None
    items: list[dict[str, Any]] = []
    for raw in _as_list(storages):
        entry = _as_dict(raw)
        space = _as_dict(entry.get("space"))
        items.append(
            {
                "id": entry.get("storage"),
                "type": entry.get("type"),
                "active": entry.get("active"),
                "content": entry.get("content"),
                "free_bytes": space.get("free"),
                "total_bytes": space.get("total"),
            }
        )
    return items


def _task_payloads(tasks: list | None, limit: int = 20) -> list[dict[str, Any]] | None:
    """Laufende Node-Tasks (gekuerzt, max. ``limit`` Eintraege)."""
    if tasks is None:
        return None
    items: list[dict[str, Any]] = []
    for raw in _as_list(tasks)[:limit]:
        entry = _as_dict(raw)
        items.append(
            {
                "upid": entry.get("upid"),
                "type": entry.get("type"),
                "status": entry.get("status"),
                "pid": entry.get("pid"),
                "start": entry.get("start", entry.get("pstart")),
                "user": entry.get("user"),
            }
        )
    return items


def _cluster_payload(health: dict | None, cluster_node_names: list[str] | None) -> dict[str, Any] | None:
    """Cluster-/Quorum-Info; None => keine Cluster-Daten ermittelbar.

    ``cluster_node_names == []`` ist eine EVIDENZ (Standalone, /cluster
    ohne Mitglieder) und liefert daher ``is_cluster=False`` — nicht None.
    """
    if not health and cluster_node_names is None:
        return None
    payload: dict[str, Any] = {}
    if health:
        payload.update(
            {
                "quorum": health.get("quorum"),
                "total": health.get("total"),
                "live": health.get("live"),
                "write_quorum": health.get("write_quorum"),
                "quorum_ok": health.get("quorum_ok"),
                "votes": [
                    {"node": _as_dict(v).get("node"), "votes": _as_dict(v).get("votes")}
                    for v in _as_list(health.get("nodes"))
                ],
            }
        )
    if cluster_node_names is not None:
        payload["members"] = cluster_node_names
        payload["is_cluster"] = len(cluster_node_names) > 1
    return payload


def _snapshot_payloads(snapshots: list | None) -> list[str] | None:
    """Snapshot-Namen; None = Anfrage nicht moeglich (Rechte/Fehler)."""
    if snapshots is None:
        return None
    names = [str(_as_dict(item).get("snapshot")) for item in _as_list(snapshots) if _as_dict(item).get("snapshot")]
    return names


def _vm_disk_payloads(config: dict) -> list[dict[str, Any]] | None:
    """Virtuelle Laufwerke aus der VM-Config (scsiN/ideN/sataN)."""
    disks: list[dict[str, Any]] = []
    for key in sorted(config):
        bare = key.split("[", 1)[0]
        if not _VM_DISK_RE.match(bare):
            continue
        value = config.get(key)
        if not isinstance(value, str) or not value:
            continue
        file_part = value.split(",", 1)[0]
        param_part = value.split(",", 1)[1] if "," in value else ""
        params = dict(part.split("=", 1) for part in param_part.split(",") if "=" in part)
        disks.append(
            {
                "device": key,
                "file": file_part or None,
                "storage": file_part.split(":", 1)[0] if ":" in file_part else None,
                "size_bytes": parse_pve_size(params.get("size")),
                "cache": params.get("cache"),
                "backup": params.get("backup"),
                "media": params.get("media"),
            }
        )
    return disks or None


def _network_payloads(config: dict) -> list[dict[str, Any]] | None:
    """Netzwerk-Interfaces aus der Config (net0..: Key=Value-Paare).

    VM:  'virtio=AA:..,bridge=vmbr0,firewall=1'
    LXC: 'name=eth0,hwaddr=AA:..,ip=10.0.0.5/24,bridge=vmbr0'
    """
    nets: list[dict[str, Any]] = []
    for key in sorted(config):
        bare = key.split("[", 1)[0]
        if not _NET_RE.match(bare):
            continue
        value = config.get(key)
        if not isinstance(value, str) or not value:
            continue
        segments = value.split(",")
        head = segments[0]
        model = head.split("=", 1)[1] if "=" in head else head
        params = dict(part.split("=", 1) for part in segments[1:] if "=" in part)
        nets.append(
            {
                "device": key,
                "model": model,
                "mac": params.get("hwaddr"),
                "bridge": params.get("bridge"),
                "ip": params.get("ip"),
                "firewall": params.get("firewall"),
            }
        )
    return nets or None


# --------------------------------------------------------------------- records

def node_record(
    node_entry: dict,
    node_detail: dict | None,
    node_status: dict | None,
    storages: list | None,
    tasks: list | None,
    cluster_health: dict | None,
    *,
    cluster_node_names: list[str] | None,
    observed_at: datetime,
) -> ResourceRecord:
    """Node-Resource (external_id = Node-Name)."""
    entry = _as_dict(node_entry)
    detail = _as_dict(node_detail)
    status = _as_dict(node_status)
    name = str(entry.get("id") or detail.get("id") or "unknown")
    raw_status = entry.get("status") or detail.get("status")
    quorum_ok = quorum_ok_from(cluster_health)
    record_status, note = map_node_status(raw_status, quorum_ok=quorum_ok)

    memory = _as_dict(status.get("memory"))
    ip_addresses: list[dict[str, Any]] = []
    for raw in _as_list(status.get("ipaddress")):
        item = _as_dict(raw)
        ip_addresses.append({"address": item.get("address"), "iface": item.get("iface"), "family": item.get("family")})

    payload: dict[str, Any] = {
        "source": "proxmox_api",
        "node": name,
        "status_raw": raw_status,
        "pve_version": entry.get("pveversion") or detail.get("pveversion") or detail.get("version"),
        "arch": entry.get("arch") or detail.get("arch"),
        "cpu_model": entry.get("cpuinfo") or detail.get("cpuinfo"),
        "cpu_count": entry.get("cpuinfo_count") or detail.get("cores") or status.get("maxcpu"),
        "memory_total_bytes": memory.get("total") or status.get("maxmem"),
        "memory_used_bytes": memory.get("used"),
        "cpu_usage": status.get("cpu"),
        "load_average": status.get("loadavg"),
        "uptime_seconds": status.get("uptime"),
        "disk": status.get("disk"),
        "ip_addresses": ip_addresses or None,
        "storages": _storage_payloads(storages),
        "tasks": _task_payloads(tasks),
        "cluster": _cluster_payload(cluster_health, cluster_node_names),
        "note": note,
    }
    return ResourceRecord(
        resource_type=ResourceType.NODE,
        external_id=name,
        name=name,
        status=record_status,
        payload=payload,
        observed_at=observed_at,
    )


def vm_record(
    list_entry: dict,
    config: dict | None,
    snapshots: list | None,
    *,
    node: str,
    observed_at: datetime,
) -> ResourceRecord:
    """QEMU-VM-Resource (external_id = VMID, cluster-eindeutig)."""
    entry = _as_dict(list_entry)
    cfg = _as_dict(config)
    vmid = entry.get("vmid")
    external_id = str(vmid) if vmid is not None else "unknown"
    name = str(entry.get("name") or f"vm-{external_id}")

    memory_total = entry.get("maxmem")  # bytes (Liste)
    if memory_total is None:
        memory_total = mb_to_bytes(cfg.get("memory"))  # config: MB

    payload: dict[str, Any] = {
        "source": "proxmox_api",
        "vmid": vmid,
        "node": node,
        "status_raw": entry.get("status"),
        "cpu_cores_configured": cfg.get("cores") or entry.get("cpus"),
        "cpu_sockets": cfg.get("sockets"),
        "cpu_model": cfg.get("cpu"),
        "cpu_usage": entry.get("cpu"),
        "memory_total_bytes": memory_total,
        "memory_used_bytes": entry.get("mem"),
        "uptime_seconds": entry.get("uptime"),
        "disk_read_bytes": entry.get("diskread"),
        "disk_write_bytes": entry.get("diskwrite"),
        "disks": _vm_disk_payloads(cfg) if cfg else None,
        "network": _network_payloads(cfg) if cfg else None,
        "snapshots": _snapshot_payloads(snapshots),
        "onboot": cfg.get("onboot"),
        "ostype": cfg.get("ostype"),
        "tags": entry.get("tags"),
        "pool": entry.get("pool") or cfg.get("pool"),
    }
    return ResourceRecord(
        resource_type=ResourceType.VM,
        external_id=external_id,
        name=name,
        status=map_compute_status(entry.get("status")),
        payload=payload,
        observed_at=observed_at,
        parent_external_id=node,
        parent_resource_type=ResourceType.NODE,
        relation_type="runs_on",
    )


def lxc_record(
    list_entry: dict,
    config: dict | None,
    snapshots: list | None,
    *,
    node: str,
    observed_at: datetime,
) -> ResourceRecord:
    """LXC-Container-Resource (external_id = CT-ID/upid, cluster-eindeutig)."""
    entry = _as_dict(list_entry)
    cfg = _as_dict(config)
    cid = entry.get("cid")
    external_id = str(cid) if cid is not None else "unknown"
    name = str(entry.get("name") or cfg.get("hostname") or f"lxc-{external_id}")

    memory_total = entry.get("maxmemory")  # bytes (Liste)
    if memory_total is None:
        memory_total = mb_to_bytes(cfg.get("memory"))

    payload: dict[str, Any] = {
        "source": "proxmox_api",
        "cid": cid,
        "node": node,
        "status_raw": entry.get("status"),
        "cpu_cores_configured": cfg.get("cores"),
        "cpu_usage": entry.get("cpu"),
        "memory_total_bytes": memory_total,
        "memory_used_bytes": entry.get("memory"),
        "uptime_seconds": entry.get("uptime"),
        "disk_read_bytes": entry.get("diskread"),
        "disk_write_bytes": entry.get("diskwrite"),
        "rootfs": cfg.get("rootfs"),
        "ostype": cfg.get("ostype"),
        "hostname": cfg.get("hostname"),
        "unprivileged": cfg.get("unprivileged"),
        "network": _network_payloads(cfg) if cfg else None,
        "snapshots": _snapshot_payloads(snapshots),
        "onboot": cfg.get("onboot"),
    }
    return ResourceRecord(
        resource_type=ResourceType.LXC,
        external_id=external_id,
        name=name,
        status=map_compute_status(entry.get("status")),
        payload=payload,
        observed_at=observed_at,
        parent_external_id=node,
        parent_resource_type=ResourceType.NODE,
        relation_type="runs_on",
    )
