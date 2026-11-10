"""Tailscale-Integration: zwei klar getrennte Zugriffsmodelle (Agent 4, R1).

Wichtig: **Management-API und lokale Client-Info sind separate Dinge**
(QUELLENBASIERT VERIFIZIERT, Stand R1 — siehe docs/agent-reports/R1-telemetry.md):

- **Modus 'api' (Tailnet-Management-API):** ``api.tailscale.com/api/v2/``
  mit API-Key (Bearer über ``secret_ref``). Liefert alle Devices des
  Tailnets. Benötigt ``extra['tailnet']`` (z. B. ``beispiel.ts.net``).
  Read-only: nur ``GET /api/v2/tailnet/{tailnet}/devices``.

- **Modus 'local' (lokaler tailscaled-Daemon, Local API):**
  ``GET /localapi/v0/status`` liefert den ``ipnstate.Status`` des lokalen
  Nodes (``Self`` + ``Peer(s)``). Zugriff je Plattform:

  * Linux: Unix-Socket (``extra['local_socket']``, Default
    ``/var/run/tailscale/tailscaled.sock``) — Auth über SO_PEERCRED,
    d. h. nur lokale User mit Daemon-Zugriff.
  * Windows/Loopback-HTTP: ``http://localhost:<port>`` (Default-Port
    41112; der alte Port 4112 ist veraltet). Optionales Basic-Auth per
    ``tailscale debug local-creds`` (Secret als ``user:pass`` oder
    nur Passwort = Basic-Auth mit leerem User).
  * Der Host-Header muss ``local-tailscaled.sock`` sein — das erzwingt
    die Local API gegen fremde Requests.

  Die Local API ist nach Tailscale-Dokumentation **keine stabile,
  offizielle Schnittstelle** (kann sich zwischen Releases ändern);
  HCC nutzt daher nur die lesenden, weithin eingesetzten Endpunkte
  ``status`` und ``whois`` und behandelt Feldänderungen tolerant
  (fehlende Felder => keine Metrik, statt erfundenen Werten).

Read-only: es werden ausschließlich GET-Requests ausgesendet.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx

from app.adapters.base import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterState,
    AdapterStatus,
    BaseAdapter,
    MetricsRecord,
    MetricValue,
    ResourceRecord,
    SecretsProvider,
)
from app.adapters.errors import AdapterApiError, AdapterAuthError, AdapterConfigError
from app.integrations.monitoring.httputil import build_async_client, request_json
from app.integrations.registry import register
from app.models.integrations import AdapterKind
from app.models.resources import ResourceStatus, ResourceType

__all__ = ["TailscaleMode", "TailscaleAdapter"]

_LOCAL_SOCKET_DEFAULT = "/var/run/tailscale/tailscaled.sock"
_LOCAL_API_HOST_HEADER = "local-tailscaled.sock"
_MAX_PEERS = 500


class TailscaleMode(StrEnum):
    """Zugriffsmodell (bewusste Trennung Management-API vs. lokale Info)."""

    API = "api"  # api.tailscale.com (Tailnet-Management)
    LOCAL = "local"  # lokaler tailscaled-Daemon (Local API)


def _parse_ts(value: Any) -> datetime | None:
    """ISO-8601-Zeitstempel (Management-API liefert z. B. '2025-01-02T03:04:05Z')."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


@register
class TailscaleAdapter(BaseAdapter):
    """Read-only-Adapter für Tailscale (Management-API oder lokale Local API)."""

    kind = AdapterKind.TAILSCALE

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # Tests: MockTransport (ersatzweise auch UDS-simulierend)
        self._transport = transport

    # -- Konfiguration / Modus -------------------------------------------

    def _mode(self, config: AdapterConfig) -> TailscaleMode:
        raw = str(config.extra.get("tailscale_mode") or "").strip().lower()
        if raw:
            try:
                return TailscaleMode(raw)
            except ValueError:
                raise AdapterConfigError(
                    f"Ungültiges extra.tailscale_mode '{raw}' (erlaubt: api, local)",
                    details={"known": [m.value for m in TailscaleMode]},
                ) from None
        # Heuristik: tailnet gesetzt -> Management-API, sonst lokaler Daemon
        return TailscaleMode.API if config.extra.get("tailnet") else TailscaleMode.LOCAL

    def _client(self, config: AdapterConfig, secrets: SecretsProvider) -> httpx.AsyncClient:
        mode = self._mode(config)
        headers: dict[str, str] = {}
        if mode is TailscaleMode.API:
            if not config.secret_ref:
                raise AdapterConfigError(
                    "Tailscale-API-Modus benötigt einen API-Key (secret_ref)"
                )
            key = secrets.get(config.secret_ref)
            if key is None:
                raise AdapterAuthError("Tailscale-API-Key nicht gesetzt (Secret-Referenz ohne Wert)")
            headers["Authorization"] = f"Bearer {key}"
            if not config.base_url:
                return build_async_client(
                    config, transport=self._transport, base_url="https://api.tailscale.com", default_headers=headers
                )
            return build_async_client(config, transport=self._transport, default_headers=headers)
        # Local API
        socket_path = config.extra.get("local_socket")
        if socket_path:
            if not socket_path.startswith("/"):
                raise AdapterConfigError(
                    "Tailscale: extra.local_socket muss ein absoluter Pfad sein"
                )
            if self._transport is None:
                # HTTP über Unix-Socket: Host-Header muss local-tailscaled.sock sein
                transport = httpx.AsyncHTTPTransport(uds=socket_path)
                return httpx.AsyncClient(
                    timeout=httpx.Timeout(config.timeout_seconds, connect=config.timeout_seconds),
                    headers={**headers, "Host": _LOCAL_API_HOST_HEADER},
                    transport=transport,
                    base_url="http://local-tailscaled.sock",
                )
            return build_async_client(
                config, transport=self._transport, base_url="http://local-tailscaled.sock", default_headers=headers
            )
        port = int(config.extra.get("local_api_port") or 41112)
        base = f"http://127.0.0.1:{port}"
        # Optionales Basic-Auth ('user:pass' via 'tailscale debug local-creds')
        if config.secret_ref:
            secret = secrets.get(config.secret_ref)
            if secret is None:
                raise AdapterAuthError("Local-API-Auth nicht gesetzt (Secret-Referenz ohne Wert)")
            user, _, password = secret.partition(":")
            if not user:
                user, password = "", password
            token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
        if self._transport is not None:
            return build_async_client(config, transport=self._transport, base_url=base, default_headers=headers)
        return build_async_client(
            config, transport=None, base_url=base, default_headers=headers
        )

    # -- IntegrationAdapter-Protokoll --------------------------------------

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        mode = self._mode(config)
        async with self._client(config, secrets) as client:
            if mode is TailscaleMode.API:
                tailnet = config.extra.get("tailnet")
                if not tailnet:
                    raise AdapterConfigError("Tailscale-API-Modus benötigt extra.tailnet")
                _, payload = await request_json(
                    client, "GET", f"/api/v2/tailnet/{tailnet}/devices", params={"perpage": 1}
                )
                body = payload if isinstance(payload, dict) else {}
                devices = body.get("devices")
                if not isinstance(devices, list):
                    raise AdapterApiError("Tailscale-API: Antwort ohne Device-Liste")
                return AdapterStatus(
                    state=AdapterState.OK,
                    message="Tailscale Management-API erreichbar",
                    api_version="v2",
                    checked_at=datetime.now(UTC),
                )
            _, payload = await request_json(client, "GET", "/localapi/v0/status", params={"peers": "false"})
        body = payload if isinstance(payload, dict) else None
        if body is None or "BackendState" not in body:
            raise AdapterApiError("Tailscale Local API: unerwartete Status-Antwort")
        return AdapterStatus(
            state=AdapterState.OK,
            message=f"Tailscale Local API erreichbar (BackendState {body.get('BackendState')})",
            api_version="localapi v0",
            checked_at=datetime.now(UTC),
        )

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        status = await self.verify(config, secrets)
        mode = self._mode(config)
        features = ["verify", "health", "discover", "metrics"]
        if mode is TailscaleMode.LOCAL:
            features.append("availability")
        return AdapterCapabilities(
            features=features,
            api_version=status.api_version,
            extra={"mode": mode.value},
        )

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        mode = self._mode(config)
        now = datetime.now(UTC)
        if mode is TailscaleMode.API:
            async with self._client(config, secrets) as client:
                tailnet = config.extra.get("tailnet")
                if not tailnet:
                    raise AdapterConfigError("Tailscale-API-Modus benötigt extra.tailnet")
                _, payload = await request_json(client, "GET", f"/api/v2/tailnet/{tailnet}/devices")
            devices = payload.get("devices") if isinstance(payload, dict) else None
            devices = devices if isinstance(devices, list) else []
            for device in devices[:_MAX_PEERS]:
                if not isinstance(device, dict) or device.get("id") is None:
                    continue
                device_id = str(device["id"])
                names = device.get("name")
                names = names if isinstance(names, list) else []
                name = str(names[0]) if names else str(device.get("hostname") or device_id)
                online = device.get("online")
                status = (
                    ResourceStatus.HEALTHY if online
                    else ResourceStatus.DOWN if online is False
                    else ResourceStatus.UNKNOWN
                )
                yield ResourceRecord(
                    resource_type=ResourceType.TAILNET_NODE,
                    external_id=device_id,
                    name=name,
                    status=status,
                    payload={
                        "origin": "tailscale management api",
                        "tailnet": tailnet,
                        "hostname": device.get("hostname"),
                        "addresses": device.get("addresses"),
                        "online": online,
                        "last_seen": _parse_ts(device.get("lastSeen")),
                    },
                    observed_at=now,
                )
            return

        async with self._client(config, secrets) as client:
            _, payload = await request_json(client, "GET", "/localapi/v0/status")
        body = payload if isinstance(payload, dict) else {}
        peers = body.get("Peers") or body.get("Peer") or {}
        peers = peers if isinstance(peers, dict) else {}
        for key, peer in list(peers.items())[:_MAX_PEERS]:
            if not isinstance(peer, dict):
                continue
            node_id = peer.get("ID")
            external_id = str(node_id) if node_id is not None else str(key)
            hosts = peer.get("TailscaleIPs")
            hosts = hosts if isinstance(hosts, list) else []
            name = str(peer.get("HostName") or (hosts[0] if hosts else external_id))
            online = peer.get("Online")
            status = (
                ResourceStatus.HEALTHY if online
                else ResourceStatus.DOWN if online is False
                else ResourceStatus.UNKNOWN
            )
            yield ResourceRecord(
                resource_type=ResourceType.TAILNET_NODE,
                external_id=external_id,
                name=name,
                status=status,
                payload={
                    "origin": "tailscale local api",
                    "tailscale_ips": [str(ip) for ip in hosts],
                    "dns_name": peer.get("DNSName"),
                    "online": online,
                    "node_id": node_id,
                },
                observed_at=now,
            )
        # lokaler Node selbst
        self_status = body.get("Self")
        if isinstance(self_status, dict) and self_status.get("ID") is not None:
            hosts = self_status.get("TailscaleIPs")
            hosts = hosts if isinstance(hosts, list) else []
            name = str(self_status.get("HostName") or self_status.get("ID"))
            yield ResourceRecord(
                resource_type=ResourceType.TAILNET_NODE,
                external_id=str(self_status["ID"]),
                name=name,
                status=ResourceStatus.HEALTHY,
                payload={
                    "origin": "tailscale local api",
                    "role": "self",
                    "tailscale_ips": [str(ip) for ip in hosts],
                    "online": self_status.get("Online"),
                },
                observed_at=now,
            )

    async def collect(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        resource_type: ResourceType,
        external_id: str,
    ) -> MetricsRecord:
        """Basis-Info zu einem Tailnet-Node (online-Status, letzte Aktivität)."""
        if resource_type is not ResourceType.TAILNET_NODE:
            raise AdapterConfigError(
                f"Tailscale: collect() unterstützt nur tailnet_node, nicht '{resource_type.value}'"
            )
        mode = self._mode(config)
        if mode is TailscaleMode.API:
            tailnet = config.extra.get("tailnet")
            if not tailnet:
                raise AdapterConfigError("Tailscale-API-Modus benötigt extra.tailnet")
            async with self._client(config, secrets) as client:
                _, payload = await request_json(
                    client, "GET", f"/api/v2/tailnet/{tailnet}/devices/{external_id}"
                )
            body = payload if isinstance(payload, dict) else {}
            online = body.get("online")
            metrics: dict[str, MetricValue] = {}
            if online is True:
                metrics["online"] = MetricValue(value=1.0, unit="bool")
            elif online is False:
                metrics["online"] = MetricValue(value=0.0, unit="bool")
            last_seen = _parse_ts(body.get("lastSeen"))
            if last_seen is not None:
                # Sekunden seit letzter Sichtung (nur positiv => ehrlich)
                age = (datetime.now(UTC) - last_seen).total_seconds()
                if age >= 0:
                    metrics["seconds_since_last_seen"] = MetricValue(value=age, unit="seconds")
            return MetricsRecord(
                external_id=external_id,
                resource_type=resource_type,
                metrics=metrics,
                collected_at=datetime.now(UTC),
            )

        # Local API: Node aus /status finden
        async with self._client(config, secrets) as client:
            _, payload = await request_json(client, "GET", "/localapi/v0/status")
        body = payload if isinstance(payload, dict) else {}
        peers = body.get("Peers") or body.get("Peer") or {}
        peers = peers if isinstance(peers, dict) else {}
        peer = None
        self_status = body.get("Self")
        for key, value in peers.items():
            if not isinstance(value, dict):
                continue
            if str(value.get("ID")) == external_id or key == external_id:
                peer = value
                break
        if peer is None and isinstance(self_status, dict) and str(self_status.get("ID")) == external_id:
            peer = self_status
        if peer is None:
            raise AdapterApiError(
                f"Tailscale: Node '{external_id}' nicht im lokalen Status gefunden"
            )
        metrics = {}
        online = peer.get("Online")
        if online is True:
            metrics["online"] = MetricValue(value=1.0, unit="bool")
        elif online is False:
            metrics["online"] = MetricValue(value=0.0, unit="bool")
        rx = peer.get("RxBytes")
        if isinstance(rx, (int, float)) and not isinstance(rx, bool):
            metrics["rx_bytes"] = MetricValue(value=float(rx), unit="bytes")
        tx = peer.get("TxBytes")
        if isinstance(tx, (int, float)) and not isinstance(tx, bool):
            metrics["tx_bytes"] = MetricValue(value=float(tx), unit="bytes")
        return MetricsRecord(
            external_id=external_id,
            resource_type=resource_type,
            metrics=metrics,
            collected_at=datetime.now(UTC),
        )
