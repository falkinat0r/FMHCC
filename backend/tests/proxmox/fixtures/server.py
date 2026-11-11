"""Fake Proxmox-API-Server fuer Tests (Agent 3, R1).

Simuliert die Proxmox api2/json-Antwort-Envelope

    {"data": ..., "status": "OK", "messages": [], "statuscode": 200, "time": ...}

sowie die relevanten Fehler- und Degradations-Szenarien (401/403/404/5xx,
fehlendes 'data', Nicht-JSON, Netzwerk-/TLS-/Timeout-Fehler, flaky 503,
Cluster-/Quorum-Varianten, asynchrone UPID-Antworten).

Der Server wird per ``httpx.MockTransport`` in den Tests eingebunden —
es findet KEIN Netzwerkzugriff statt. Alle Daten sind Test-Fixturen
(Testnetz 10.0.0.0/24, fiktive Hostnamen) und enthalten keine Secrets:
Das Token ist ein dokumentierter Test-Placeholder.
"""

from __future__ import annotations

import asyncio
import re
import ssl
from typing import Any

import httpx

# Erwarteter Authorization-Header (Test-Placeholder, KEIN echtes Secret).
# Format laut Proxmox-Doku: PVEAPIToken=<user>@<realm>!<token-id>=<secret>
VALID_TOKEN_HEADER = "PVEAPIToken=hcc@pve!hcc-test=0123456789abcdef01234789abcdef012345"

_API_ROOT = "/api2/json"


def _ok(data: Any, statuscode: int = 200) -> httpx.Response:
    """Positiv-Envelope im PVE-Format."""
    return httpx.Response(
        statuscode,
        json={
            "data": data,
            "status": "OK",
            "messages": [],
            "statuscode": statuscode,
            "time": 1730000000.0,
        },
    )


def _err(status: int, messages: list[str] | str) -> httpx.Response:
    """Fehler-Envelope im PVE-Format."""
    if isinstance(messages, str):
        messages = [messages]
    return httpx.Response(
        status,
        json={"data": None, "status": "ERROR", "messages": messages, "statuscode": status},
    )


def make_upid(node: str, resource_id: str, verb: str) -> str:
    """Plausible UPID-Task-ID (Format: UPID:node:pid:time:shortid:action:param:...)."""
    return f"UPID:{node}:00001234:59141b2c:aa11bb22cc33dd44:{resource_id}:{verb}:00000000"


class FakeProxmoxServer:
    """In-Memory Proxmox-API mit Szenario-Feldern und Request-Logs.

    - ``request_log``: (METHOD, path ohne /api2/json) pro Anfrage.
    - ``action_log``:  Pfade aller POST-Aktionen (Schreib-Requests).
    - ``network_error``: 'unreachable' | 'tls' | 'timeout' | None.
    - ``flaky_paths``:  path -> Anzahl verbleibender 503-Antworten.
    - ``forbidden_paths`` / ``malformed_paths`` / ``no_data_paths``:
      403- bzw. fehlerhafte-Antwort-Szenarien pro exaktem Pfad.
    """

    def __init__(self) -> None:
        self.version: dict[str, Any] = {"version": "9.1.2", "release": "9.1.2"}
        self.nodes: list[dict] | Any = []
        self.node_details: dict[str, dict] = {}
        self.node_status: dict[str, dict] = {}
        self.node_storage: dict[str, list] = {}
        self.node_tasks: dict[str, list] = {}
        self.qemu: dict[str, list[dict]] = {}
        self.qemu_config: dict[str, dict] = {}  # "node:vmid" -> config
        self.qemu_snapshots: dict[str, list[dict]] = {}  # "node:vmid" -> [snapshot]
        self.containers: dict[str, list[dict]] = {}
        self.container_config: dict[str, dict] = {}  # "node:cid" -> config
        self.lxc_snapshots: dict[str, list[dict]] = {}  # "node:cid" -> [snapshot]
        # None = Endpunkt nicht vorhanden (404); [] = Standalone-Evidenz
        self.cluster: list[dict] | None = []
        self.cluster_health: dict | None = None
        # Aktionen: "qemu:node:vmid:verb" / "lxc:node:cid:verb" -> UPID
        self.actions: dict[str, str] = {}
        self.action_errors: dict[str, int] = {}  # "api:node:id:verb" -> HTTP-Status
        self.task_results: dict[str, dict] = {}  # upid -> Task-Status
        self.network_error: str | None = None
        self.forbidden_paths: set[str] = set()
        self.malformed_paths: set[str] = set()
        self.no_data_paths: set[str] = set()
        self.flaky_paths: dict[str, int] = {}
        self.delay_seconds: float = 0.0
        self.request_log: list[tuple[str, str]] = []
        self.action_log: list[str] = []

    # ------------------------------------------------------------------ helper

    def paths(self) -> list[str]:
        return [path for _method, path in self.request_log]

    def count(self, path: str) -> int:
        return sum(1 for _m, p in self.request_log if p == path)

    # ------------------------------------------------------------------ transport

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """httpx.MockTransport-Handler (simuliert den Proxmox-Host)."""
        path = request.url.path
        if path.startswith(_API_ROOT):
            path = path[len(_API_ROOT) :]
        self.request_log.append((request.method, path))

        if self.network_error == "unreachable":
            raise httpx.ConnectError("connection refused (Test-Simulation)")
        if self.network_error == "tls":
            ssl_exc = ssl.SSLError(1, "certificate verify failed: self-signed certificate (Test)")
            try:
                raise httpx.ConnectError("TLS-Verifizierung fehlgeschlagen (Test-Simulation)") from ssl_exc
            except httpx.ConnectError:
                raise
        if self.network_error == "timeout":
            raise httpx.ReadTimeout("read timed out (Test-Simulation)")
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        if path != "/version" and request.headers.get("authorization", "") != VALID_TOKEN_HEADER:
            return _err(401, "authentication failed - invalid API token (Test-Simulation)")
        if path in self.forbidden_paths:
            return _err(403, "permission denied (Test-Simulation)")
        if path in self.malformed_paths:
            return httpx.Response(200, content=b"<<< defekte Antwort, kein JSON (Test-Simulation) >>>")
        if path in self.no_data_paths:
            return httpx.Response(200, json={"status": "OK", "messages": []})

        remaining = self.flaky_paths.get(path)
        if remaining is not None:
            if remaining <= 1:
                del self.flaky_paths[path]
            else:
                self.flaky_paths[path] = remaining - 1
            return _err(503, "service temporarily unavailable (Test-Simulation)")

        if request.method == "GET":
            return self._route_get(path, request.url.params)
        if request.method == "POST":
            return self._route_post(path)
        return _err(405, "method not allowed")

    # ------------------------------------------------------------------ routing

    def _route_get(self, path: str, params: dict[str, str]) -> httpx.Response:
        if path == "/version":
            return _ok(self.version)
        if path == "/nodes":
            return _ok(self.nodes)
        if path == "/cluster":
            if self.cluster is None:
                return _err(404, "no such resource: /cluster (Test-Simulation)")
            return _ok(self.cluster)
        if path == "/cluster/health":
            if self.cluster_health is None:
                return _err(404, "no such resource: /cluster/health (Test-Simulation)")
            return _ok(self.cluster_health)
        if path == "/cluster/resources":
            return _ok(self._cluster_resources(params))

        match = re.match(r"^/nodes/([^/]+)$", path)
        if match:
            node = match.group(1)
            detail = self.node_details.get(node)
            return _ok(detail) if detail is not None else _err(404, f"unknown node '{node}'")
        match = re.match(r"^/nodes/([^/]+)/(status|storage|tasks)$", path)
        if match:
            node, kind = match.group(1), match.group(2)
            data = getattr(self, f"node_{kind}").get(node)
            return _ok(data) if data is not None else _err(404, f"unknown node '{node}'")

        if path.endswith("/qemu"):
            node = path.split("/")[2]
            return _ok(self.qemu.get(node, []))
        if path.endswith("/containers"):
            node = path.split("/")[2]
            return _ok(self.containers.get(node, []))

        match = re.match(r"^/nodes/([^/]+)/qemu/(\d+)$", path)
        if match:
            node, vmid = match.group(1), int(match.group(2))
            entry = next((e for e in self.qemu.get(node, []) if e.get("vmid") == vmid), None)
            return _ok(entry) if entry is not None else _err(404, "unknown vm")
        match = re.match(r"^/nodes/([^/]+)/lxc/(\d+)$", path)
        if match:
            node, cid = match.group(1), int(match.group(2))
            entry = next((e for e in self.containers.get(node, []) if e.get("cid") == cid), None)
            return _ok(entry) if entry is not None else _err(404, "unknown container")

        match = re.match(r"^/nodes/([^/]+)/qemu/(\d+)/config$", path)
        if match:
            key = f"{match.group(1)}:{match.group(2)}"
            return _ok(self.qemu_config[key]) if key in self.qemu_config else _err(404, "unknown config")
        match = re.match(r"^/nodes/([^/]+)/qemu/(\d+)/snapshot$", path)
        if match:
            key = f"{match.group(1)}:{match.group(2)}"
            return _ok(self.qemu_snapshots[key]) if key in self.qemu_snapshots else _err(404, "unknown resource")
        match = re.match(r"^/nodes/([^/]+)/containers/(\d+)/config$", path)
        if match:
            key = f"{match.group(1)}:{match.group(2)}"
            return _ok(self.container_config[key]) if key in self.container_config else _err(404, "unknown config")
        match = re.match(r"^/nodes/([^/]+)/lxc/(\d+)/snapshot$", path)
        if match:
            key = f"{match.group(1)}:{match.group(2)}"
            return _ok(self.lxc_snapshots[key]) if key in self.lxc_snapshots else _err(404, "unknown resource")

        match = re.match(r"^/nodes/([^/]+)/tasks/([^/]+)$", path)
        if match:
            upid = match.group(2)
            return _ok(self.task_results[upid]) if upid in self.task_results else _err(404, "unknown task")

        return _err(404, f"unknown endpoint '{path}' (Test-Simulation)")

    def _cluster_resources(self, params: dict[str, str]) -> list[dict]:
        """/cluster/resources?type=vm|container&vmid=N (funktioniert auf Standalone wie im Cluster)."""
        wanted_type = params.get("type", "")
        wanted_vmid = params.get("vmid")
        entries: list[dict] = []
        if wanted_type == "vm":
            for node, items in self.qemu.items():
                for entry in items:
                    entries.append(
                        {
                            "vmid": entry.get("vmid"),
                            "node": node,
                            "type": "vm",
                            "status": entry.get("status"),
                            "name": entry.get("name"),
                        }
                    )
        elif wanted_type == "container":
            for node, items in self.containers.items():
                for entry in items:
                    entries.append(
                        {
                            "vmid": entry.get("cid"),
                            "node": node,
                            "type": "container",
                            "status": entry.get("status"),
                            "name": entry.get("name"),
                        }
                    )
        if wanted_vmid:
            entries = [e for e in entries if str(e.get("vmid")) == wanted_vmid]
        return entries

    def _route_post(self, path: str) -> httpx.Response:
        match = re.match(r"^/nodes/([^/]+)/qemu/(\d+)/status/(start|shutdown|restart)$", path)
        if match is not None:
            api, verb = "qemu", match.group(3)
            node, resource_id = match.group(1), match.group(2)
        else:
            match = re.match(r"^/nodes/([^/]+)/lxc/(\d+)/(start|stop|restart)$", path)
            if match is None:
                return _err(404, f"unknown action endpoint '{path}' (Test-Simulation)")
            api, verb = "lxc", match.group(3)
            node, resource_id = match.group(1), match.group(2)

        self.action_log.append(path)
        key = f"{api}:{node}:{resource_id}:{verb}"
        if key in self.action_errors:
            return _err(self.action_errors[key], f"action '{key}' failed (Test-Simulation)")
        upid = self.actions.get(key)
        if upid is None:
            return _err(404, f"unknown resource '{resource_id}' on '{node}' (Test-Simulation)")
        return _ok(upid)


# --------------------------------------------------------------------- scenarios


def _node_entry(node: str, *, status: str = "online", version: str, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": node,
        "status": status,
        "type": "proxmox",
        "pveversion": version,
        "arch": "x86_64",
        "cpuinfo": "Intel(R) Core(TM) i7-4790 CPU @ 3.60GHz",
        "cpuinfo_count": 8,
        "maxmem": 34359738368,
        "maxcpu": 8,
    }
    entry.update(extra)
    return entry


def _node_detail(node: str, *, status: str = "online", version: str) -> dict[str, Any]:
    return {
        "id": node,
        "status": status,
        "pveversion": version,
        "arch": "x86_64",
        "version": version,
        "cores": 8,
        "cpuinfo": "Intel(R) Core(TM) i7-4790 CPU @ 3.60GHz",
        "memory": {"total": 34359738368, "used": 21474836480},
    }


def _node_status(node: str, *, ip: str) -> dict[str, Any]:
    return {
        "cpu": 12.5,
        "disk": {"used": 4398046511104, "total": 5497558138880, "space": 1099511627776},
        "ipaddress": [{"address": ip, "iface": "vmbr0", "family": "ipv4"}],
        "loadavg": [0.42, 0.31, 0.25],
        "memory": {"total": 34359738368, "used": 21474836480},
        "maxmem": 34359738368,
        "maxcpu": 8,
        "uptime": 518400,
        "version": "9.1.2",
    }


def _node_storage() -> list[dict]:
    return [
        {
            "storage": "local",
            "type": "dir",
            "active": 1,
            "content": ["images", "vms", "iso", "snippets"],
            "space": {"free": 4398046511104, "total": 5497558138880},
        },
        {
            "storage": "nfs-backup",
            "type": "nfs",
            "active": 1,
            "content": ["backup", "vztmpl"],
            "space": {"free": 1099511627776, "total": 2199023255552},
        },
    ]


def standalone_scenario(*, version: str = "9.1.2") -> FakeProxmoxServer:
    """Standalone-Host pve1: 3 VMs (101 running, 102 stopped, 103 paused),
    2 LXC-Container (201 running, 202 stopped), Quorum nicht anwendbar."""
    server = FakeProxmoxServer()
    server.version = {"version": version, "release": version}
    server.nodes = [_node_entry("pve1", version=version)]
    server.node_details = {"pve1": _node_detail("pve1", version=version)}
    server.node_status = {"pve1": _node_status("pve1", ip="10.0.0.2")}
    server.node_storage = {"pve1": _node_storage()}
    server.node_tasks = {
        "pve1": [
            {
                "upid": make_upid("pve1", "101", "start"),
                "type": "qemu",
                "status": "started",
                "pid": 4321,
                "start": 1730000000,
                "user": "hcc@pve",
            }
        ]
    }
    server.qemu = {
        "pve1": [
            {
                "vmid": 101,
                "name": "atlas",
                "status": "running",
                "maxmem": 4294967296,
                "mem": 3221225472,
                "cpu": 45.2,
                "cpus": 4,
                "uptime": 86400,
                "diskread": 1073741824,
                "diskwrite": 536870912,
            },
            {
                "vmid": 102,
                "name": "poseidon",
                "status": "stopped",
                "maxmem": 2147483648,
                "mem": 0,
                "cpu": 0,
                "cpus": 2,
            },
            {
                "vmid": 103,
                "name": "athena",
                "status": "paused",
                "maxmem": 3145728000,
                "mem": 2576980377,
                "cpu": 0.5,
                "cpus": 2,
            },
        ]
    }
    server.qemu_config = {
        "pve1:101": {
            "cores": 4,
            "sockets": 1,
            "cpu": "host",
            "memory": 4096,
            "onboot": 1,
            "ostype": "l26",
            "bios": "seabios",
            "scsi0": "local-lvm:vm-101-disk-0,size=32G,cache=writeback,backup=1",
            "ide2": "local:iso/images/windows.iso,media=cdrom,size=4G",
            "net0": "virtio=AA:BB:CC:DD:EE:01,bridge=vmbr0,firewall=1",
        },
        "pve1:102": {
            "cores": 2,
            "sockets": 1,
            "memory": 2048,
            "scsi0": "local:vm-102-disk-0,size=16G",
            "net0": "virtio=AA:BB:CC:DD:EE:02,bridge=vmbr0",
        },
        "pve1:103": {
            "cores": 2,
            "memory": 3000,
            "scsi0": "local:vm-103-disk-0,size=24G,cache=unsafe",
            "net0": "e1000=AA:BB:CC:DD:EE:03,bridge=vmbr1",
        },
    }
    server.qemu_snapshots = {
        "pve1:101": [{"snapshot": "pre-upgrade"}, {"snapshot": "snap-2026-11-01"}],
        "pve1:102": [],
        "pve1:103": [],
    }
    server.containers = {
        "pve1": [
            {
                "cid": 201,
                "name": "phole",
                "status": "running",
                "maxmemory": 2147483648,
                "memory": 1073741824,
                "cpu": 5.0,
                "uptime": 432000,
                "diskread": 536870912,
                "diskwrite": 104857600,
            },
            {
                "cid": 202,
                "name": "vault",
                "status": "stopped",
                "maxmemory": 1073741824,
                "memory": 0,
                "cpu": 0,
            },
        ]
    }
    server.container_config = {
        "pve1:201": {
            "cores": 2,
            "memory": 2048,
            "hostname": "phole",
            "ostype": "x86_64",
            "unprivileged": 1,
            "onboot": 1,
            "rootfs": "local:1",
            "net0": "name=eth0,hwaddr=AA:BB:CC:DD:FF:01,ip=10.0.0.31/24,bridge=vmbr0",
        },
        "pve1:202": {
            "cores": 1,
            "memory": 1024,
            "hostname": "vault",
            "rootfs": "local:1",
            "net0": "name=eth0,hwaddr=AA:BB:CC:DD:FF:02,ip=10.0.0.32/24",
        },
    }
    server.lxc_snapshots = {
        "pve1:201": [{"snapshot": "before-migration"}],
        "pve1:202": [],
    }
    server.cluster = []  # Evidenz: Standalone (kein Cluster-Mitglied)
    server.cluster_health = None
    server.actions = {
        f"qemu:pve1:{vmid}:{verb}": make_upid("pve1", str(vmid), verb)
        for vmid in (101, 102, 103)
        for verb in ("start", "shutdown", "restart")
    }
    server.actions.update(
        {
            f"lxc:pve1:{cid}:{verb}": make_upid("pve1", str(cid), verb)
            for cid in (201, 202)
            for verb in ("start", "stop", "restart")
        }
    )
    server.task_results = {
        upid: {"status": "stopped", "exitstatus": "OK"} for upid in server.actions.values()
    }
    return server


def cluster_scenario(
    *, quorum_ok: int = 1, version: str = "9.1.2"
) -> FakeProxmoxServer:
    """3-Node-Cluster: pve1/pve2 online (pve2 haeut VM 104), pve3 offline.

    ``quorum_ok=0`` simuliert fehlendes Quorum (degradierte Online-Nodes).
    """
    server = standalone_scenario(version=version)
    server.nodes = [
        _node_entry("pve1", version=version),
        _node_entry("pve2", version=version),
        _node_entry("pve3", status="offline", version=version),
    ]
    server.node_details = {
        "pve1": _node_detail("pve1", version=version),
        "pve2": _node_detail("pve2", version=version),
        # pve3 offline: keine Details (und keine Requests dorthin erwartet)
    }
    server.node_status = {
        "pve1": _node_status("pve1", ip="10.0.0.2"),
        "pve2": _node_status("pve2", ip="10.0.0.3"),
    }
    server.node_storage["pve2"] = _node_storage()
    server.node_tasks = {
        "pve1": server.node_tasks.get("pve1", []),
        "pve2": [],
    }
    server.qemu = {
        "pve1": server.qemu["pve1"],
        "pve2": [
            {
                "vmid": 104,
                "name": "hermes",
                "status": "running",
                "maxmem": 2147483648,
                "mem": 1610612736,
                "cpu": 3.1,
                "cpus": 2,
                "uptime": 172800,
            }
        ],
        "pve3": [],
    }
    server.qemu_config["pve2:104"] = {
        "cores": 2,
        "sockets": 1,
        "memory": 2048,
        "scsi0": "local:vm-104-disk-0,size=12G",
        "net0": "virtio=AA:BB:CC:DD:EE:04,bridge=vmbr0",
    }
    server.qemu_snapshots["pve2:104"] = []
    server.cluster = [{"id": name, "type": "pve"} for name in ("pve1", "pve2", "pve3")]
    server.cluster_health = {
        "quorum_ok": quorum_ok,
        "quorum": 2,
        "total": 2,
        "write_quorum": 2,
        "live": 2,
        "nodes": [
            {"node": "pve1", "votes": 2, "status": "online"},
            {"node": "pve2", "votes": 2, "status": "online"},
            {"node": "pve3", "votes": 0, "status": "offline"},
        ],
    }
    server.actions.update(
        {f"qemu:pve2:104:{verb}": make_upid("pve2", "104", verb) for verb in ("start", "shutdown", "restart")}
    )
    return server
