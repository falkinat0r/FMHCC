"""ProxmoxClient-Tests (Agent 3, R1) — gegen FakeProxmoxServer (MockTransport).

Deckung: Auth-Header-Format, Envelope-Loesung, Retry (nur GET),
keine POST-Retry, Fehlermauerung (401/403/404/5xx/Nicht-JSON),
get_optional/get_tolerant-Semantik, Rate-Limiter.
"""

from __future__ import annotations

import time

import pytest

from app.adapters.errors import (
    AdapterApiError,
    AdapterAuthError,
    AdapterState,
    AdapterTimeoutError,
    AdapterUnreachableError,
)
from app.integrations.proxmox.client import _RateLimiter
from app.integrations.proxmox.config import parse_token
from tests.proxmox.conftest import client_request, run
from tests.proxmox.fixtures import standalone_scenario


def test_get_nodes_happy_path_and_auth_header() -> None:
    server = standalone_scenario()
    nodes = client_request(server, lambda client: client.get("/nodes"))
    assert [node["id"] for node in nodes] == ["pve1"]
    # Server akzeptiert nur den exakten PVEAPIToken-Header — erfuellt per Konstruktion
    assert server.request_log[0] == ("GET", "/nodes")


def test_get_unauthenticated_version_but_authenticated_nodes() -> None:
    server = standalone_scenario()

    async def _scenario(client):
        version = await client.get("/version")
        nodes = await client.get("/nodes")
        return version, nodes

    version, nodes = client_request(server, _scenario)
    assert version["version"] == "9.1.2"
    assert isinstance(nodes, list)


def test_retry_get_on_503_succeeds_after_backoff() -> None:
    server = standalone_scenario()
    server.flaky_paths = {"/nodes": 1}  # erster Versuch 503, zweiter OK
    nodes = client_request(server, lambda client: client.get("/nodes"), max_retries="1")
    assert [node["id"] for node in nodes] == ["pve1"]
    assert server.count("/nodes") == 2


def test_retry_get_exhausted_raises_api_error() -> None:
    server = standalone_scenario()
    server.flaky_paths = {"/nodes": 2}  # beide Versuche 503
    with pytest.raises(AdapterApiError) as exc_info:
        client_request(server, lambda client: client.get("/nodes"), max_retries="1")
    assert exc_info.value.state is AdapterState.API_ERROR
    assert exc_info.value.http_status == 503
    assert server.count("/nodes") == 2  # max_retries=1 => exakt 2 Versuche


def test_post_action_never_retried() -> None:
    server = standalone_scenario()
    server.action_errors = {"qemu:pve1:101:start": 503}

    with pytest.raises(AdapterApiError) as exc_info:
        client_request(server, lambda client: client.post("/nodes/pve1/qemu/101/status/start"), max_retries="5")
    assert exc_info.value.state is AdapterState.API_ERROR
    assert exc_info.value.http_status == 503
    # POST: exakt ein Versuch trotz hoher max_retries
    assert sum(1 for method, _ in server.request_log if method == "POST") == 1


def test_unreachable_maps_to_adapter_unreachable() -> None:
    server = standalone_scenario()
    server.network_error = "unreachable"
    with pytest.raises(AdapterUnreachableError) as exc_info:
        client_request(server, lambda client: client.get("/nodes"))
    assert exc_info.value.state is AdapterState.UNREACHABLE
    assert exc_info.value.details.get("tls") is False


def test_tls_certificate_error_is_classified() -> None:
    server = standalone_scenario()
    server.network_error = "tls"
    with pytest.raises(AdapterUnreachableError) as exc_info:
        client_request(server, lambda client: client.get("/nodes"))
    assert exc_info.value.state is AdapterState.UNREACHABLE
    assert exc_info.value.details.get("tls") is True


def test_timeout_maps_to_adapter_timeout() -> None:
    server = standalone_scenario()
    server.network_error = "timeout"
    with pytest.raises(AdapterTimeoutError) as exc_info:
        client_request(server, lambda client: client.get("/nodes"), max_retries="2")
    assert exc_info.value.state is AdapterState.TIMEOUT
    # Timeout wird NICHT retried
    assert server.count("/nodes") == 1


def make_wrong_secret_client(server) -> object:
    """Client mit gueltigem Format, aber falschem Secret (=> 401-Szenario)."""
    from httpx import MockTransport

    from app.integrations.proxmox.client import ProxmoxClient
    from tests.proxmox.conftest import make_options

    token = parse_token("hcc@pve!hcc-test=ffffffffffffffffffffffffffffffff")
    return ProxmoxClient(make_options(), token, transport=MockTransport(server.handle))


async def _get_nodes(client) -> object:
    async with client as closed:
        return await closed.get("/nodes")


def test_invalid_token_raises_auth_error_401() -> None:
    server = standalone_scenario()
    client = make_wrong_secret_client(server)
    with pytest.raises(AdapterAuthError) as exc_info:
        run(_get_nodes(client))
    assert exc_info.value.state is AdapterState.AUTH_FAILED
    assert exc_info.value.details.get("http_status") == 401


def test_forbidden_raises_auth_error_403() -> None:
    server = standalone_scenario()
    server.forbidden_paths = {"/nodes"}
    with pytest.raises(AdapterAuthError) as exc_info:
        client_request(server, lambda client: client.get("/nodes"))
    assert exc_info.value.state is AdapterState.AUTH_FAILED
    assert exc_info.value.details.get("http_status") == 403


def test_malformed_response_not_json() -> None:
    server = standalone_scenario()
    server.malformed_paths = {"/nodes"}
    with pytest.raises(AdapterApiError) as exc_info:
        client_request(server, lambda client: client.get("/nodes"))
    assert exc_info.value.state is AdapterState.API_ERROR
    assert "JSON" in exc_info.value.message


def test_response_without_data_field() -> None:
    server = standalone_scenario()
    server.no_data_paths = {"/nodes"}
    with pytest.raises(AdapterApiError) as exc_info:
        client_request(server, lambda client: client.get("/nodes"))
    assert exc_info.value.state is AdapterState.API_ERROR
    assert "data" in exc_info.value.message


def test_client_error_details_do_not_leak_secret() -> None:
    server = standalone_scenario()
    client = make_wrong_secret_client(server)
    with pytest.raises(AdapterAuthError) as exc_info:
        run(_get_nodes(client))
    assert "ffffffffffffffffffffffffffffffff" not in exc_info.value.message
    assert "ffffffffffffffffffffffffffffffff" not in str(exc_info.value.details)


# ---------------------------------------------------------------- optional GETs


def test_get_optional_403_returns_none() -> None:
    server = standalone_scenario()
    server.forbidden_paths = {"/nodes/pve1"}
    assert client_request(server, lambda client: client.get_optional("/nodes/pve1")) is None


def test_get_optional_404_returns_none() -> None:
    server = standalone_scenario()
    assert client_request(server, lambda client: client.get_optional("/nodes/ghost")) is None


def test_get_optional_503_still_raises() -> None:
    server = standalone_scenario()
    server.flaky_paths = {"/nodes/pve1": 99}
    with pytest.raises(AdapterApiError):
        client_request(server, lambda client: client.get_optional("/nodes/pve1"), max_retries="1")


def test_get_optional_auth_401_still_raises() -> None:
    server = standalone_scenario()
    client = make_wrong_secret_client(server)
    with pytest.raises(AdapterAuthError):
        run(_get_optional(client, "/nodes/pve1"))


async def _get_optional(client, path: str) -> object:
    async with client as closed:
        return await closed.get_optional(path)


def test_get_tolerant_swallows_any_adapter_error() -> None:
    server = standalone_scenario()
    server.network_error = "unreachable"
    assert client_request(server, lambda client: client.get_tolerant("/nodes/pve1/status")) is None
    server.network_error = None
    server.malformed_paths = {"/nodes/pve1/status"}
    assert client_request(server, lambda client: client.get_tolerant("/nodes/pve1/status")) is None


def test_get_tolerant_returns_data_when_ok() -> None:
    server = standalone_scenario()
    data = client_request(server, lambda client: client.get_tolerant("/nodes/pve1/status"))
    assert isinstance(data, dict)
    assert data["memory"]["total"] == 34359738368


# ------------------------------------------------------------------ rate limiter


def test_rate_limiter_enforces_minimal_spacing() -> None:
    limiter = _RateLimiter(10.0)  # 100 ms Abstand pro Request
    start = time.monotonic()

    async def _acquire() -> None:
        for _ in range(4):
            await limiter.acquire()

    run(_acquire())
    elapsed = time.monotonic() - start
    assert elapsed >= 0.3  # 3 Wartepausen zu je >=100 ms


def test_rate_limiter_disabled_for_zero_rate() -> None:
    limiter = _RateLimiter(0.0)
    start = time.monotonic()
    run(_acquire_many(limiter))
    assert time.monotonic() - start < 0.05


async def _acquire_many(limiter: _RateLimiter) -> None:
    for _ in range(10):
        await limiter.acquire()
