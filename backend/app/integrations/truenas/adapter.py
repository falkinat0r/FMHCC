"""TrueNAS-Integration: Read-only-Adapter fuer die REST-API v2.0 (Agent 4, R1).

QUELLENBASIERT VERIFIZIERT (Stand R1, Details in docs/agent-reports/R1-telemetry.md):

- **Base-Path:** ``/api/v2.0/`` (TrueNAS SCALE 24.04 / 24.10 / 25.04 / 25.10;
  CORE 13.x). **Ab TrueNAS 26.0 ist die REST-API entfernt** (nur noch
  WebSocket) — der Adapter meldet das dann als Version-unsupported, statt
  zu stubben.
- **Auth:** kein Login-Endpoint, keine Session-Cookies. Pro Request:
  ``Authorization: Basic base64(user:pass)`` (Secret als ``user:pass``)
  oder ``Authorization: Bearer <api_key>`` (Secret ohne ``:``). Beachten:
  2FA aktiv => Basic nicht verfuegbar; ab 25.04 gilt fuer API-Keys das
  Server-AAL-Niveau.
- **Antworten:** ROHES JSON (kein Envelope!). Fehler: 422
  ``{"message": ..., "errno": ...}``, 404 ``{"message": ...}``,
  401/403 Klartext.
- **Endpoints (lesend):**
  * ``GET /api/v2.0/openapi.json`` (ohne Auth) — API-Pruesfung/Versionsgate
  * ``GET /api/v2.0/system/info`` — Feld ``version`` (Vollstring)
  * ``GET /api/v2.0/pool`` — Pool-Liste inkl. Health/Size/Scan
  * ``GET /api/v2.0/pool/dataset`` — Datasets (ZFS-Properties)
  * ``GET /api/v2.0/disk`` — Disks (identifier als Primarschluessel)
  * ``GET /api/v2.0/smart/test/results`` — SMART-Selftest-Ergebnisse
- **ZFS-Events:** nur per WebSocket (kein REST-Streaming) — R1 nutzt
  Polling der Pool-Daten (Scan-Zustand), kein Event-Abonnement.
"""

from __future__ import annotations

import base64
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
from app.adapters.errors import (
    AdapterApiError,
    AdapterAuthError,
    AdapterConfigError,
    AdapterVersionError,
)
from app.integrations.monitoring.httputil import build_async_client, request_json
from app.integrations.registry import register
from app.models.integrations import AdapterKind
from app.models.resources import ResourceStatus, ResourceType

__all__ = ["TruenasAdapter"]

_MAX_DATASETS_IN_DISCOVER = 200


def _pool_status_to_resource(status: str, healthy: Any, warning: Any) -> ResourceStatus:
    """Pool-Status (zpool) + healthy/warning-Flags => ResourceStatus.

    Ehrlich: nur klare Zustände werden gemappt; alles andere => UNKNOWN
    (keine erfundenen Erfolgswerte).
    """
    if healthy is True and warning is not True:
        return ResourceStatus.HEALTHY
    raw = str(status or "").upper()
    if raw == "ONLINE":
        return ResourceStatus.HEALTHY if healthy is True else ResourceStatus.UNKNOWN
    if raw == "DEGRADED":
        return ResourceStatus.DEGRADED
    if raw in ("FAULTED", "OFFLINE", "UNAVAIL"):
        return ResourceStatus.DOWN
    if healthy is False:
        return ResourceStatus.DOWN
    if warning is True:
        return ResourceStatus.DEGRADED
    return ResourceStatus.UNKNOWN


def _disk_status_from_smart(smart_entry: dict[str, Any] | None) -> ResourceStatus:
    """SMART-Selftest-Resultate => Disk-Status (FAIL-Test => DEGRADED)."""
    if smart_entry is None:
        return ResourceStatus.UNKNOWN
    tests = smart_entry.get("tests")
    tests = tests if isinstance(tests, list) else []
    for test in tests:
        if not isinstance(test, dict):
            continue
        status = str(test.get("status", "")).upper()
        if status == "FAILED":
            return ResourceStatus.DEGRADED
    if tests and all(str(t.get("status", "")).upper() == "SUCCESS" for t in tests if isinstance(t, dict)):
        return ResourceStatus.HEALTHY
    return ResourceStatus.UNKNOWN


def _prop_number(entry: dict[str, Any], prop: str) -> float | None:
    """ZFS-Dataset-Property lesen: ``entry[prop]["value"]`` (oft {'parsed','value'}).

    Nicht-numerische Werte ('none', null, …) => None (keine erfundene Metrik).
    """
    raw = entry.get(prop)
    value: Any = raw.get("value") if isinstance(raw, dict) else raw
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


@register
class TruenasAdapter(BaseAdapter):
    """Read-only-Adapter fuer TrueNAS (REST-API v2.0, SCALE 24.04–25.10)."""

    kind = AdapterKind.TRUENAS

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    # -- Client / Auth -----------------------------------------------------

    def _headers(self, config: AdapterConfig, secrets: SecretsProvider) -> dict[str, str]:
        """Basic (Secret 'user:pass') oder Bearer (Secret ohne ':' = API-Key)."""
        if not config.secret_ref:
            raise AdapterConfigError("TrueNAS: Zugangsdaten nicht konfiguriert (secret_ref fehlt)")
        secret = secrets.get(config.secret_ref)
        if secret is None:
            raise AdapterAuthError("TrueNAS-Credentials nicht gesetzt (Secret-Referenz ohne Wert)")
        if ":" in secret:
            user, _, password = secret.partition(":")
            if not user or not password:
                raise AdapterConfigError("TrueNAS: Credentials-Maske 'user:pass' unvollstaendig")
            token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
            return {"Authorization": f"Basic {token}"}
        return {"Authorization": f"Bearer {secret}"}

    def _client(self, config: AdapterConfig, secrets: SecretsProvider) -> httpx.AsyncClient:
        return build_async_client(config, transport=self._transport, default_headers=self._headers(config, secrets))

    @staticmethod
    def _require_base_url(config: AdapterConfig) -> None:
        if not config.base_url:
            raise AdapterConfigError("TrueNAS: base_url nicht konfiguriert")

    async def _probe_rest_api(self, config: AdapterConfig) -> str | None:
        """Auth-freies OpenAPI-Endpoint pruefen (Versionsgate 26.0+ => kein REST).

        401/403 hier ist kein Versionshinweis (openapi.json sollte auth-frei
        sein) => wird wie jeder andere Nicht-200 als API-Fehler gemappt.
        """
        self._require_base_url(config)
        async with build_async_client(config, transport=self._transport) as client:
            status, _ = await request_json(client, "GET", "/api/v2.0/openapi.json", raise_for_error=False)
        if status in (404, 405):
            raise AdapterVersionError(
                "TrueNAS: REST-API v2.0 nicht verfuegbar (ab TrueNAS 26.0 nur noch WebSocket)"
            )
        if status != 200:
            raise AdapterApiError(
                f"TrueNAS: OpenAPI-Endpoint antwortet mit HTTP {status}", http_status=status
            )
        return "v2.0"

    # -- IntegrationAdapter-Protokoll --------------------------------------

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        """REST-API-Pruefung + Auth via /system/info (Feld 'version')."""
        await self._probe_rest_api(config)
        async with self._client(config, secrets) as client:
            _, payload = await request_json(client, "GET", "/api/v2.0/system/info")
        body = payload if isinstance(payload, dict) else {}
        version = str(body.get("version") or "").strip()
        if not version:
            raise AdapterApiError("TrueNAS: /system/info ohne Versionsangabe")
        return AdapterStatus(
            state=AdapterState.OK,
            message=f"TrueNAS erreichbar ({version})",
            api_version="v2.0",
            checked_at=datetime.now(UTC),
        )

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        status = await self.verify(config, secrets)
        return AdapterCapabilities(
            features=["verify", "health", "source_status", "discover", "metrics"],
            api_version=status.api_version,
            extra={"api": "rest v2.0"},
        )

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        """System (HOST), Pools, Disks (mit SMART), Datasets."""
        await self._probe_rest_api(config)
        now = datetime.now(UTC)
        async with self._client(config, secrets) as client:
            _, info_payload = await request_json(client, "GET", "/api/v2.0/system/info")
            _, pools_payload = await request_json(client, "GET", "/api/v2.0/pool")
            _, disks_payload = await request_json(client, "GET", "/api/v2.0/disk")
            _, datasets_payload = await request_json(client, "GET", "/api/v2.0/pool/dataset")
            _, smart_payload = await request_json(client, "GET", "/api/v2.0/smart/test/results")

        info = info_payload if isinstance(info_payload, dict) else {}
        pools = pools_payload if isinstance(pools_payload, list) else []
        disks = disks_payload if isinstance(disks_payload, list) else []
        datasets = datasets_payload if isinstance(datasets_payload, list) else []
        smart_results = smart_payload if isinstance(smart_payload, list) else []
        smart_by_disk = {
            str(entry.get("disk")): entry for entry in smart_results if isinstance(entry, dict)
        }

        # System
        version = str(info.get("version") or "unknown")
        yield ResourceRecord(
            resource_type=ResourceType.HOST,
            external_id="system",
            name=str(info.get("hostname") or "truenas"),
            status=ResourceStatus.HEALTHY,
            payload={
                "origin": "truenas",
                "version": version,
                "physmem_bytes": info.get("physmem"),
                "cores": info.get("cores"),
                "uptime_seconds": info.get("uptime_seconds"),
                "loadavg": info.get("loadavg"),
                "boottime": info.get("boottime"),
            },
            observed_at=now,
        )

        # Pools
        for pool in pools:
            if not isinstance(pool, dict) or pool.get("name") is None:
                continue
            status = _pool_status_to_resource(
                str(pool.get("status") or ""), pool.get("healthy"), pool.get("warning")
            )
            scan = pool.get("scan")
            scan = scan if isinstance(scan, dict) else {}
            yield ResourceRecord(
                resource_type=ResourceType.POOL,
                external_id=str(pool.get("name")),
                name=str(pool.get("name")),
                status=status,
                payload={
                    "origin": "truenas",
                    "pool_id": pool.get("id"),
                    "zpool_status": pool.get("status"),
                    "healthy": pool.get("healthy"),
                    "warning": pool.get("warning"),
                    "size_bytes": pool.get("size"),
                    "allocated_bytes": pool.get("allocated"),
                    "free_bytes": pool.get("free"),
                    "scan_state": scan.get("state"),
                    "scan_percentage": scan.get("percentage"),
                    "scan_errors": scan.get("errors"),
                },
                observed_at=now,
            )

        # Disks
        for disk in disks:
            if not isinstance(disk, dict) or not disk.get("identifier"):
                continue
            disk_name = str(disk.get("name") or disk.get("identifier"))
            status = _disk_status_from_smart(smart_by_disk.get(disk_name))
            yield ResourceRecord(
                # DISK ist kein frozen ResourceType => OTHER (Disk-Identitaet
                # steht im external_id/Payload; Typ-Erweiterung nur per Proposal)
                resource_type=ResourceType.OTHER,
                external_id=str(disk.get("identifier")),
                name=f"{disk_name} ({disk.get('model') or 'unknown model'})",
                status=status,
                payload={
                    "origin": "truenas",
                    "name": disk_name,
                    "model": disk.get("model"),
                    "serial": disk.get("serial"),
                    "size_bytes": disk.get("size"),
                    "pool": disk.get("pool"),
                    "type": disk.get("type"),
                },
                observed_at=now,
            )

        # Datasets (gekappt, Inventar nicht sprengen)
        for dataset in datasets[:_MAX_DATASETS_IN_DISCOVER]:
            if not isinstance(dataset, dict) or not dataset.get("name"):
                continue
            used = _prop_number(dataset, "used")
            available = _prop_number(dataset, "available")
            quota = _prop_number(dataset, "quota")
            yield ResourceRecord(
                resource_type=ResourceType.DATASET,
                external_id=str(dataset.get("name")),
                name=str(dataset.get("name")),
                status=ResourceStatus.UNKNOWN,
                payload={
                    "origin": "truenas",
                    "type": dataset.get("type"),
                    "mountpoint": dataset.get("mountpoint"),
                    "used_bytes": used,
                    "available_bytes": available,
                    "quota_bytes": quota,
                    "encrypted": dataset.get("encrypted"),
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
        """Ressourcenmetriken je Typ (Pool-Gruesse, Disk-SMART, Host-Load, Dataset-Nutzung)."""
        await self._probe_rest_api(config)
        async with self._client(config, secrets) as client:
            if resource_type is ResourceType.POOL:
                _, payload = await request_json(
                    client, "GET", "/api/v2.0/pool", params={"name__eq": external_id}
                )
                pools = payload if isinstance(payload, list) else []
                pool = next((p for p in pools if isinstance(p, dict) and str(p.get("name")) == external_id), None)
                if pool is None:
                    raise AdapterApiError(f"TrueNAS: Pool '{external_id}' nicht gefunden")
                metrics: dict[str, MetricValue] = {}
                for field, name, unit in (
                    ("size", "pool_size", "bytes"),
                    ("allocated", "pool_allocated", "bytes"),
                    ("free", "pool_free", "bytes"),
                ):
                    if value := _as_number(pool.get(field)):
                        metrics[name] = MetricValue(value=value, unit=unit)
                scan = pool.get("scan")
                if isinstance(scan, dict) and _is_number(scan.get("percentage")):
                    metrics["pool_scan_progress"] = MetricValue(value=float(scan["percentage"]), unit="percent")
            elif resource_type is ResourceType.OTHER:
                _, payload = await request_json(
                    client, "GET", "/api/v2.0/disk", params={"identifier__eq": external_id}
                )
                disks = payload if isinstance(payload, list) else []
                disk = next(
                    (d for d in disks if isinstance(d, dict) and str(d.get("identifier")) == external_id), None
                )
                if disk is None:
                    raise AdapterApiError(f"TrueNAS: Disk '{external_id}' nicht gefunden")
                metrics = {}
                if value := _as_number(disk.get("size")):
                    metrics["disk_size"] = MetricValue(value=value, unit="bytes")
                _, smart_payload = await request_json(client, "GET", "/api/v2.0/smart/test/results")
                smart_results = smart_payload if isinstance(smart_payload, list) else []
                entry = next(
                    (e for e in smart_results if isinstance(e, dict) and e.get("disk") == disk.get("name")),
                    None,
                )
                tests = entry.get("tests") if isinstance(entry, dict) else None
                tests = tests if isinstance(tests, list) else []
                if tests:
                    failed = sum(
                        1 for t in tests if isinstance(t, dict) and str(t.get("status", "")).upper() == "FAILED"
                    )
                    metrics["smart_failed_tests"] = MetricValue(value=float(failed), unit="count")
                    metrics["smart_test_count"] = MetricValue(value=float(len(tests)), unit="count")
            elif resource_type is ResourceType.HOST:
                _, payload = await request_json(client, "GET", "/api/v2.0/system/info")
                info = payload if isinstance(payload, dict) else {}
                metrics = {}
                loadavg = info.get("loadavg")
                loadavg = loadavg if isinstance(loadavg, list) else []
                if len(loadavg) >= 3:
                    for index, name in enumerate(("load1", "load5", "load15")):
                        if _is_number(loadavg[index]):
                            metrics[name] = MetricValue(value=float(loadavg[index]), unit="ratio")
                if value := _as_number(info.get("uptime_seconds")):
                    metrics["uptime"] = MetricValue(value=value, unit="seconds")
                if value := _as_number(info.get("physmem")):
                    metrics["physmem"] = MetricValue(value=value, unit="bytes")
            elif resource_type is ResourceType.DATASET:
                # query-Filter statt Pfad-ID (sicher gegen Pfad-Injection)
                _, payload = await request_json(
                    client, "GET", "/api/v2.0/pool/dataset", params={"name__eq": external_id}
                )
                datasets = payload if isinstance(payload, list) else []
                dataset = next(
                    (d for d in datasets if isinstance(d, dict) and str(d.get("name")) == external_id), None
                )
                if dataset is None:
                    raise AdapterApiError(f"TrueNAS: Dataset '{external_id}' nicht gefunden")
                metrics = {}
                for prop, name in (("used", "dataset_used"), ("available", "dataset_available"), ("quota", "dataset_quota")):
                    if value := _prop_number(dataset, prop):
                        metrics[name] = MetricValue(value=value, unit="bytes")
            else:
                raise AdapterConfigError(
                    f"TrueNAS: collect() unterstuetzt '{resource_type.value}' nicht "
                    "(erlaubt: pool, disk, host, dataset)"
                )
        return MetricsRecord(
            external_id=external_id,
            resource_type=resource_type,
            metrics=metrics,
            collected_at=datetime.now(UTC),
        )


def _as_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
