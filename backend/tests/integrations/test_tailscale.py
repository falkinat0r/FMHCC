"""Tailscale-Adapter-Tests (fixture-basiert, Agent 4, R1).

Szenarien: Management-API-Modus (available/auth/discover/collect) und
Lokal-Daemon-Modus (Local API status/Peers/Self), Modus-Unterscheidung,
not_configured (fehlender API-Key), Auth-Fehler, Timeout.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.adapters.errors import (
    AdapterAuthError,
    AdapterConfigError,
    AdapterState,
    AdapterTimeoutError,
)
from app.integrations.tailscale.adapter import TailscaleAdapter, TailscaleMode
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

FX = load_fixture("tailscale.json")


def api_handler() -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v2/tailnet/lan.ts.net/devices":
            return json_response(FX["devices"])
        if path == "/api/v2/tailnet/lan.ts.net/devices/101":
            return json_response(FX["device_101"])
        return json_response({"error": "unroutet"}, status_code=404)

    return handler


def local_handler() -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/localapi/v0/status":
            return json_response(FX["local_status"])
        return json_response({"error": "unroutet"}, status_code=404)

    return handler


def adapter(handler: Callable[[httpx.Request], httpx.Response]) -> TailscaleAdapter:
    return TailscaleAdapter(transport=httpx.MockTransport(handler))


# -- Modus-API (api.tailscale.com) ------------------------------------------


def test_api_verify_available() -> None:
    config = make_config(secret_ref="TS_KEY", extra={"tailscale_mode": "api", "tailnet": "lan.ts.net"})
    status = run(adapter(api_handler()).verify(config, make_secrets({"TS_KEY": "tskey-fixture"})))
    assert status.state is AdapterState.OK
    assert status.api_version == "v2"


def test_api_requires_secret_ref() -> None:
    config = make_config(extra={"tailscale_mode": "api", "tailnet": "lan.ts.net"})
    with pytest.raises(AdapterConfigError):
        run(adapter(api_handler()).verify(config, make_secrets()))


def test_api_auth_failed() -> None:
    config = make_config(secret_ref="TS_KEY", extra={"tailscale_mode": "api", "tailnet": "lan.ts.net"})
    with pytest.raises(AdapterAuthError):
        run(
            adapter(lambda request: json_response({"message": "unauthorized"}, status_code=401)).verify(
                config, make_secrets({"TS_KEY": "tskey-wrong"})
            )
        )


def test_api_missing_tailnet_is_config_error() -> None:
    config = make_config(secret_ref="TS_KEY", extra={"tailscale_mode": "api"})
    with pytest.raises(AdapterConfigError):
        run(adapter(api_handler()).verify(config, make_secrets({"TS_KEY": "tskey-fixture"})))


def test_api_discover_devices() -> None:
    config = make_config(secret_ref="TS_KEY", extra={"tailscale_mode": "api", "tailnet": "lan.ts.net"})
    records = drain(adapter(api_handler()).discover(config, make_secrets({"TS_KEY": "tskey-fixture"})))
    by_id = {r.external_id: r for r in records}
    assert set(by_id) == {"101", "102", "103"}
    assert all(r.resource_type is ResourceType.TAILNET_NODE for r in records)
    assert by_id["101"].status is ResourceStatus.HEALTHY
    assert by_id["101"].name == "office-mac"
    assert by_id["102"].status is ResourceStatus.DOWN
    assert by_id["103"].payload["hostname"] is None


def test_api_collect_device() -> None:
    config = make_config(secret_ref="TS_KEY", extra={"tailscale_mode": "api", "tailnet": "lan.ts.net"})
    record = run(adapter(api_handler()).collect(config, make_secrets({"TS_KEY": "tskey-fixture"}), ResourceType.TAILNET_NODE, "101"))
    assert record.metrics["online"].value == 1.0
    assert "seconds_since_last_seen" in record.metrics


# -- Lokal-Modus (tailscaled Local API) --------------------------------------


def test_local_verify_available() -> None:
    config = make_config(extra={"tailscale_mode": "local"})
    status = run(adapter(local_handler()).verify(config, make_secrets()))
    assert status.state is AdapterState.OK
    assert "Running" in status.message


def test_local_discover_peers_and_self() -> None:
    config = make_config(extra={"tailscale_mode": "local"})
    records = drain(adapter(local_handler()).discover(config, make_secrets()))
    by_id = {r.external_id: r for r in records}
    assert set(by_id) == {"102", "103", "101"}  # 101 = Self
    assert by_id["102"].status is ResourceStatus.HEALTHY
    assert by_id["102"].name == "office-mac"
    assert by_id["103"].status is ResourceStatus.DOWN
    assert by_id["101"].payload.get("role") == "self"


def test_local_collect_peer_metrics() -> None:
    config = make_config(extra={"tailscale_mode": "local"})
    record = run(adapter(local_handler()).collect(config, make_secrets(), ResourceType.TAILNET_NODE, "102"))
    assert record.metrics["online"].value == 1.0
    assert record.metrics["rx_bytes"].value == 123456789
    assert record.metrics["tx_bytes"].value == 987654321


def test_local_collect_unknown_node() -> None:
    config = make_config(extra={"tailscale_mode": "local"})
    from app.adapters.errors import AdapterApiError

    with pytest.raises(AdapterApiError):
        run(adapter(local_handler()).collect(config, make_secrets(), ResourceType.TAILNET_NODE, "999"))


def test_local_basic_auth_header() -> None:
    """Local-API-Auth: Secret 'pass' (oder 'user:pass') => Basic-Auth-Header."""
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return json_response(FX["local_status"])

    config = make_config(extra={"tailscale_mode": "local"}, secret_ref="TS_LOCAL_PW")
    run(adapter(handler).verify(config, make_secrets({"TS_LOCAL_PW": "fixture-local-pass"})))
    assert seen["auth"] is not None
    assert seen["auth"].startswith("Basic ")


# -- Modus-Unterscheidung / Fehler ------------------------------------------


def test_mode_detection_heuristic() -> None:
    adapter_ = adapter(api_handler())
    config_api = make_config(secret_ref="TS_KEY", extra={"tailnet": "lan.ts.net"})
    config_local = make_config()
    assert adapter_._mode(config_api) is TailscaleMode.API  # noqa: SLF001 - Test-Inspektion
    assert adapter_._mode(config_local) is TailscaleMode.LOCAL  # noqa: SLF001


def test_invalid_mode_is_config_error() -> None:
    config = make_config(extra={"tailscale_mode": "quantum"})
    with pytest.raises(AdapterConfigError):
        run(adapter(api_handler()).verify(config, make_secrets()))


def test_timeout() -> None:
    config = make_config(extra={"tailscale_mode": "local"})
    with pytest.raises(AdapterTimeoutError):
        run(adapter(timeout_handler(lambda: httpx.ReadTimeout("slow"))).verify(config, make_secrets()))


def test_collect_wrong_resource_type() -> None:
    config = make_config(extra={"tailscale_mode": "local"})
    with pytest.raises(AdapterConfigError):
        run(adapter(local_handler()).collect(config, make_secrets(), ResourceType.POOL, "tank"))
