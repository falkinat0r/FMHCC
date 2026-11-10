"""TrueNAS-Adapter-Tests (fixture-basiert, Agent 4, R1).

Szenarien: REST-v2 available + Auth (Basic user:pass), not_configured
(keine Credentials), Version-Gate (REST fehlt => 26.0+), Auth-Fehler,
Timeout, Discover (Pools mit DEGRADED/FAULTED = 'bad storage states',
Disks mit SMART, Datasets), Collect (Pool/Host/Disk/Dataset),
fehlerhafte Antworten.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.adapters.errors import (
    AdapterApiError,
    AdapterAuthError,
    AdapterConfigError,
    AdapterState,
    AdapterTimeoutError,
    AdapterVersionError,
)
from app.integrations.truenas.adapter import TruenasAdapter
from app.models.resources import ResourceStatus, ResourceType
from tests.integrations.conftest import (
    drain,
    json_response,
    load_fixture,
    make_config,
    make_secrets,
    run,
    timeout_handler,
)

FX = load_fixture("truenas.json")


def handler(
    openapi: int | dict = 200,
    system_info: dict | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    def inner(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v2.0/openapi.json":
            if openapi == 200:
                return json_response(FX["openapi"])
            return json_response({"message": "not found"}, status_code=openapi)
        if path == "/api/v2.0/system/info":
            return json_response(system_info if system_info is not None else FX["system_info"])
        if path == "/api/v2.0/pool":
            return json_response(FX["pools"])
        if path == "/api/v2.0/disk":
            return json_response(FX["disks"])
        if path == "/api/v2.0/pool/dataset":
            return json_response(FX["datasets"])
        if path == "/api/v2.0/smart/test/results":
            return json_response(FX["smart_results"])
        return json_response({"message": "unroutet"}, status_code=404)

    return inner


def adapter(routes: Callable[[httpx.Request], httpx.Response] | None = None) -> TruenasAdapter:
    return TruenasAdapter(transport=httpx.MockTransport(routes or handler()))


def creds() -> tuple:
    return make_config(
        base_url="https://nas.lan",
        secret_ref="TRUENAS_CREDS",
    ), make_secrets({"TRUENAS_CREDS": "reader:fixture-pass"})


def basic_only_handler(status_code: int) -> Callable[[httpx.Request], httpx.Response]:
    """openapi.json ist auth-frei (200); system/info antwortet mit status_code."""
    def inner(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2.0/openapi.json":
            return json_response(FX["openapi"])
        if request.url.path == "/api/v2.0/system/info":
            return json_response("Bad username or password", status_code=status_code)
        return json_response("Invalid API key", status_code=401)

    return inner


# -- Verify / Auth -----------------------------------------------------------


def test_verify_available_basic_auth() -> None:
    config, secrets = creds()
    status = run(adapter().verify(config, secrets))
    assert status.state is AdapterState.OK
    assert status.api_version == "v2.0"
    assert "24.04.2" in status.message


def test_verify_basic_header_used() -> None:
    """Secret 'user:pass' => Authorization: Basic."""
    seen: dict[str, str | None] = {}

    def inner(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2.0/system/info":
            seen["auth"] = request.headers.get("Authorization")
            return json_response(FX["system_info"])
        return json_response(FX["openapi"])

    config, secrets = creds()
    run(adapter(inner).verify(config, secrets))
    assert seen["auth"] is not None and seen["auth"].startswith("Basic ")


def test_verify_bearer_api_key() -> None:
    """Secret ohne ':' => API-Key (Bearer)."""
    seen: dict[str, str | None] = {}

    def inner(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2.0/system/info":
            seen["auth"] = request.headers.get("Authorization")
            return json_response(FX["system_info"])
        return json_response(FX["openapi"])

    config = make_config(base_url="https://nas.lan", secret_ref="TRUENAS_KEY")
    secrets = make_secrets({"TRUENAS_KEY": "fixture-api-key"})
    run(adapter(inner).verify(config, secrets))
    assert seen["auth"] == "Bearer fixture-api-key"


def test_verify_not_configured_without_secret_ref() -> None:
    config = make_config(base_url="https://nas.lan")
    with pytest.raises(AdapterConfigError):
        run(adapter().verify(config, make_secrets()))


def test_verify_secret_ref_unset() -> None:
    config = make_config(base_url="https://nas.lan", secret_ref="NICHT_GESETZT")
    with pytest.raises(AdapterAuthError):
        run(adapter().verify(config, make_secrets()))


def test_verify_bad_credentials() -> None:
    config, secrets = creds()
    with pytest.raises(AdapterAuthError):
        run(adapter(basic_only_handler(401)).verify(config, secrets))


def test_verify_rest_api_gone_is_version_unsupported() -> None:
    """TrueNAS 26.0+: REST-API entfernt => Version-unsupported, kein Stub."""
    config, secrets = creds()
    with pytest.raises(AdapterVersionError):
        run(adapter(handler(openapi=404)).verify(config, secrets))


def test_verify_no_version_field_is_api_error() -> None:
    config, secrets = creds()
    with pytest.raises(AdapterApiError):
        run(adapter(handler(system_info={"hostname": "nas"})).verify(config, secrets))


def test_verify_timeout() -> None:
    config, secrets = creds()
    with pytest.raises(AdapterTimeoutError):
        run(adapter(timeout_handler(lambda: httpx.ReadTimeout("slow"))).verify(config, secrets))


# -- Discover (inkl. bad storage states) --------------------------------------


def test_discover_system_pools_disks_datasets() -> None:
    config, secrets = creds()
    records = drain(adapter().discover(config, secrets))
    hosts = [r for r in records if r.resource_type is ResourceType.HOST]
    pools = {r.external_id: r for r in records if r.resource_type is ResourceType.POOL}
    disks = {r.external_id: r for r in records if r.resource_type is ResourceType.OTHER}
    datasets = {r.external_id: r for r in records if r.resource_type is ResourceType.DATASET}

    assert len(hosts) == 1
    assert hosts[0].payload["version"] == "TrueNAS-24.04.2"

    # Bad storage states: DEGRADED => degraded, FAULTED => down
    assert pools["tank"].status is ResourceStatus.HEALTHY
    assert pools["backup"].status is ResourceStatus.DEGRADED
    assert pools["backup"].payload["scan_errors"] == 3
    assert pools["old-media"].status is ResourceStatus.DOWN

    # Disks: SMART FAILED => degraded, RUNNING => unknown, SUCCESS => healthy
    assert disks["ata-FixtureDisk0"].status is ResourceStatus.HEALTHY
    assert disks["ata-FixtureDisk1"].status is ResourceStatus.DEGRADED
    assert disks["ata-FixtureDisk2"].status is ResourceStatus.UNKNOWN

    assert datasets["tank"].payload["used_bytes"] == 4000000000000
    assert datasets["tank"].payload["quota_bytes"] is None  # 'none' => nicht erfinden
    assert datasets["tank/data"].payload["encrypted"] is True


def test_discover_bad_pool_payload_is_unknown_not_fake() -> None:
    """Unbekannter Pool-Zustand => UNKNOWN statt erfundenem HEALTHY."""

    def inner(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2.0/pool":
            return json_response([{"id": 9, "name": "mystery", "status": "WEIRD_STATE", "healthy": None}])
        if request.url.path in ("/api/v2.0/disk", "/api/v2.0/pool/dataset", "/api/v2.0/smart/test/results"):
            return json_response([])
        return json_response(FX["system_info"] if request.url.path.endswith("system/info") else FX["openapi"])

    config, secrets = creds()
    records = drain(adapter(inner).discover(config, secrets))
    pools = [r for r in records if r.resource_type is ResourceType.POOL]
    assert pools[0].status is ResourceStatus.UNKNOWN


# -- Collect ------------------------------------------------------------------


def test_collect_pool_metrics() -> None:
    config, secrets = creds()
    record = run(adapter().collect(config, secrets, ResourceType.POOL, "backup"))
    metrics = record.metrics
    assert metrics["pool_size"].value == 6000000000000
    assert metrics["pool_allocated"].value == 5500000000000
    assert metrics["pool_free"].value == 500000000000
    assert metrics["pool_scan_progress"].value == 42.5


def test_collect_pool_not_found() -> None:
    config, secrets = creds()
    with pytest.raises(AdapterApiError):
        run(adapter().collect(config, secrets, ResourceType.POOL, "ghost"))


def test_collect_disk_smart_metrics() -> None:
    config, secrets = creds()
    record = run(adapter().collect(config, secrets, ResourceType.OTHER, "ata-FixtureDisk1"))
    metrics = record.metrics
    assert metrics["disk_size"].value == 4000000000000
    assert metrics["smart_failed_tests"].value == 1
    assert metrics["smart_test_count"].value == 2


def test_collect_host_metrics() -> None:
    config, secrets = creds()
    record = run(adapter().collect(config, secrets, ResourceType.HOST, "system"))
    metrics = record.metrics
    assert metrics["load1"].value == 0.42
    assert metrics["load5"].value == 0.51
    assert metrics["uptime"].value == 2592000
    assert metrics["physmem"].value == 34359738368


def test_collect_dataset_metrics() -> None:
    config, secrets = creds()
    record = run(adapter().collect(config, secrets, ResourceType.DATASET, "tank/data"))
    metrics = record.metrics
    assert metrics["dataset_used"].value == 1500000000000
    assert metrics["dataset_quota"].value == 2000000000000
    # 'tank/vm-images' hat used='none' => keine erfundene Metrik
    record2 = run(adapter().collect(config, secrets, ResourceType.DATASET, "tank/vm-images"))
    assert "dataset_used" not in record2.metrics


def test_collect_unknown_resource_type() -> None:
    config, secrets = creds()
    with pytest.raises(AdapterConfigError):
        run(adapter().collect(config, secrets, ResourceType.CONTAINER, "x"))
