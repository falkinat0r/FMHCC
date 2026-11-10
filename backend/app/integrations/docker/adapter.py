"""Read-only-Adapter für Docker (Agent 4, R1).

Funktionen: Container-Discovery, Containerstatus, Metadaten (inkl.
Compose-Projekt-Labels), Ressourcenverbrauch (stats), Images, Host-Metadaten.

Sicherheit:
- Zugriff nur über die in security.py definierten Modelle (Unix-Socket,
  TLS/mTLS, Loopback-TCP). Kein ungeschützter Remote-TCP-Socket.
- Nur lesende Endpoints (version, info, containers, images, stats).
- Container-IDs werden vor der Verwendung gegen das hex-Format geprüft
  (kein Pfad-Injection).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
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
from app.adapters.errors import AdapterApiError, AdapterConfigError
from app.integrations.docker.security import (
    DockerAccess,
    build_docker_transport,
    resolve_docker_access,
)
from app.integrations.monitoring.httputil import request_json
from app.integrations.registry import register
from app.models.integrations import AdapterKind
from app.models.resources import ResourceStatus, ResourceType

__all__ = ["DockerAdapter"]

_CONTAINER_ID_RE = re.compile(r"^[a-f0-9]{12,64}$")
_MAX_IMAGES_IN_PAYLOAD = 100

_DOCKER_STATE_MAP: dict[str, ResourceStatus] = {
    "running": ResourceStatus.HEALTHY,
    "paused": ResourceStatus.DEGRADED,
    "restarting": ResourceStatus.DEGRADED,
    "created": ResourceStatus.UNKNOWN,
    "exited": ResourceStatus.DOWN,
    "removing": ResourceStatus.UNKNOWN,
}


@register
class DockerAdapter(BaseAdapter):
    """Read-only-Adapter für die Docker Engine-API."""

    kind = AdapterKind.DOCKER

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # Tests: MockTransport ersetzt Socket-/TLS-Transport
        self._test_transport = transport

    def _access(self, config: AdapterConfig) -> DockerAccess:
        return resolve_docker_access(config)

    def _client(self, config: AdapterConfig) -> httpx.AsyncClient:
        access = self._access(config)
        transport = self._test_transport or build_docker_transport(access)
        return httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds, connect=config.timeout_seconds),
            headers={"User-Agent": "hcc-adapter/1.0"},
            transport=transport,
            base_url=access.base_url,
        )

    # -- IntegrationAdapter-Protokoll -------------------------------------

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        """Engine-Version abfragen (GET /version)."""
        async with self._client(config) as client:
            _, payload = await request_json(client, "GET", "/version")
        body = payload if isinstance(payload, dict) else {}
        api_version = body.get("ApiVersion") or body.get("Version")
        if not api_version:
            raise AdapterApiError("Docker: /version ohne Versionsangabe")
        return AdapterStatus(
            state=AdapterState.OK,
            message=f"Docker Engine {api_version} erreichbar",
            api_version=str(api_version),
            checked_at=datetime.now(UTC),
        )

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        access = self._access(config)
        async with self._client(config) as client:
            _, payload = await request_json(client, "GET", "/version")
        body = payload if isinstance(payload, dict) else {}
        platform = body.get("Platform")
        platform_name = platform.get("Name") if isinstance(platform, dict) else None
        return AdapterCapabilities(
            features=["verify", "health", "discover", "metrics"],
            api_version=str(body.get("ApiVersion") or body.get("Version") or ""),
            extra={
                "mode": access.mode,
                "engine": platform_name,
                "security_notes": access.security_notes,
            },
        )

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        """Docker-Host + Container (mit Compose-Zuordnung) + Image-Zusammenfassung."""
        access = self._access(config)
        now = datetime.now(UTC)
        async with self._client(config) as client:
            _, info_payload = await request_json(client, "GET", "/info")
            _, containers_payload = await request_json(client, "GET", "/containers/json", params={"all": "1"})
            _, images_payload = await request_json(client, "GET", "/images/json")

        info = info_payload if isinstance(info_payload, dict) else {}
        containers = containers_payload if isinstance(containers_payload, list) else []
        images = images_payload if isinstance(images_payload, list) else []

        yield ResourceRecord(
            resource_type=ResourceType.HOST,
            external_id="host",
            name=str(info.get("Name") or "docker-host"),
            status=ResourceStatus.HEALTHY,
            payload={
                "origin": "docker",
                "mode": access.mode,
                "server_version": info.get("ServerVersion"),
                "operating_system": info.get("OperatingSystem"),
                "architecture": info.get("Architecture"),
                "containers_summary": info.get("Containers"),
                "images_count": len(images),
                "images": [_compact_image(image) for image in images[:_MAX_IMAGES_IN_PAYLOAD]],
                "images_truncated": len(images) > _MAX_IMAGES_IN_PAYLOAD,
            },
            observed_at=now,
        )

        for container in containers:
            if not isinstance(container, dict) or not container.get("Id"):
                continue
            yield ResourceRecord(
                resource_type=ResourceType.CONTAINER,
                external_id=str(container["Id"]),
                name=_container_name(container),
                status=_DOCKER_STATE_MAP.get(str(container.get("State") or container.get("state") or ""), ResourceStatus.UNKNOWN),
                payload=_container_payload(container),
                observed_at=now,
            )

    async def collect(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        resource_type: ResourceType,
        external_id: str,
    ) -> MetricsRecord:
        """Ressourcenverbrauch eines Containers (stats, one-shot)."""
        if resource_type is not ResourceType.CONTAINER:
            raise AdapterConfigError(f"Docker: collect() unterstützt nur Container, nicht '{resource_type.value}'")
        if not _CONTAINER_ID_RE.fullmatch(external_id):
            raise AdapterConfigError(
                "Docker: ungültige Container-ID (erwartet: hex, 12–64 Zeichen)",
                details={"external_id": external_id[:16]},
            )
        async with self._client(config) as client:
            _, payload = await request_json(
                client, "GET", f"/containers/{external_id}/stats", params={"stream": "false", "one-shot": "1"}
            )
        return MetricsRecord(
            external_id=external_id,
            resource_type=resource_type,
            metrics=_parse_container_stats(payload),
            collected_at=datetime.now(UTC),
        )


def _container_name(container: dict[str, Any]) -> str:
    names = container.get("Names")
    if isinstance(names, list) and names:
        return str(names[0]).lstrip("/")
    return str(container.get("Id", "unknown"))[:12]


def _container_payload(container: dict[str, Any]) -> dict[str, Any]:
    labels = container.get("Labels")
    labels = labels if isinstance(labels, dict) else {}
    image = container.get("Image")
    started = container.get("StartedAt")
    try:
        started_at = datetime.fromisoformat(str(started).replace("Z", "+00:00")).astimezone(UTC) if started else None
    except ValueError:
        started_at = None
    return {
        "origin": "docker",
        "state": str(container.get("State") or container.get("state") or "unknown"),
        "image": str(image) if image else None,
        "image_id": container.get("ImageID"),
        "started_at": started_at,
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
        "short_id": str(container.get("Id") or container.get("ID") or "")[:12],
    }


def _compact_image(image: dict[str, Any]) -> dict[str, Any]:
    image_id = str(image.get("Id") or "")
    tags = image.get("Tags")
    tags = [str(tag) for tag in tags if tag][:3] if isinstance(tags, list) else []
    return {
        "id": image_id.rsplit(":", 1)[-1][:19] if image_id else None,
        "tags": tags,
        "size": image.get("Size"),
    }


def _parse_container_stats(payload: Any) -> dict[str, MetricValue]:
    """one-shot stats -> Metriken mit Einheiten (fehlende Felder => keine Metrik)."""
    body = payload if isinstance(payload, dict) else {}
    metrics: dict[str, MetricValue] = {}

    cpu_delta = _number(body.get("cpu_stats"), "cpu_usage", "total_usage") - _number(
        body.get("precpu_stats"), "cpu_usage", "total_usage"
    )
    system_delta = _number(body.get("cpu_stats"), "system_cpu_usage") - _number(
        body.get("precpu_stats"), "system_cpu_usage"
    )
    online_cpus = body.get("ncpus")
    if cpu_delta > 0 and system_delta > 0 and online_cpus:
        metrics["cpu_percent"] = MetricValue(
            value=cpu_delta / system_delta * float(online_cpus) * 100, unit="percent"
        )

    memory_stats = body.get("memory_stats")
    memory_stats = memory_stats if isinstance(memory_stats, dict) else {}
    if usage := _number(memory_stats, "usage"):
        metrics["memory_usage"] = MetricValue(value=usage, unit="bytes")
    if limit := _number(memory_stats, "limit"):
        metrics["memory_limit"] = MetricValue(value=limit, unit="bytes")

    networks = body.get("networks")
    networks = networks if isinstance(networks, dict) else {}
    rx = sum(float(data.get("rx_bytes") or 0) for data in networks.values() if isinstance(data, dict))
    tx = sum(float(data.get("tx_bytes") or 0) for data in networks.values() if isinstance(data, dict))
    if rx:
        metrics["network_rx"] = MetricValue(value=rx, unit="bytes")
    if tx:
        metrics["network_tx"] = MetricValue(value=tx, unit="bytes")

    # blkio-Device-Usage ist format-abhängig (Pro-Device-Dict); R1 liefert
    # bewusst keine blkio-Metrik, statt inkonsistente Werte zu erfinden.
    return metrics


def _number(node: Any, *path: str) -> float:
    """Verschachtelte Zahlen sicher lesen (Default 0)."""
    current: Any = node
    for key in path:
        if not isinstance(current, dict):
            return 0.0
        current = current.get(key)
    if isinstance(current, (int, float)) and not isinstance(current, bool):
        return float(current)
    return 0.0



