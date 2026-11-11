"""Monitoring-Backend-Tests: Grafana, Loki, Uptime Kuma + Engine
(Backend-Auswahl/Auto-Erkennung) — fixture-basiert (Agent 4, R1).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.adapters.errors import AdapterApiError, AdapterAuthError, AdapterConfigError, AdapterState
from app.integrations.monitoring.engine import MonitoringAdapter
from app.integrations.monitoring.grafana import GrafanaBackend
from app.integrations.monitoring.loki import LokiBackend
from app.integrations.monitoring.uptime_kuma import UptimeKumaBackend
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

FX = load_fixture("grafana_loki_uptime.json")


def mock(fn: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(fn)


# -- Grafana ------------------------------------------------------------------


def test_grafana_verify_available() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(FX["grafana_health_ok"])

    config = make_config(base_url="http://grafana.lan:3000")
    status = run(GrafanaBackend(transport=mock(handler)).verify(config, make_secrets()))
    assert status.state is AdapterState.OK
    assert status.api_version == "11.4.0"


def test_grafana_database_error_is_api_error_state() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(FX["grafana_health_db_error"])

    config = make_config(base_url="http://grafana.lan:3000")
    status = run(GrafanaBackend(transport=mock(handler)).verify(config, make_secrets()))
    assert status.state is AdapterState.API_ERROR


def test_grafana_token_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(FX["grafana_health_ok"])

    config = make_config(base_url="http://grafana.lan:3000", secret_ref="GF_TOKEN")
    with pytest.raises(AdapterAuthError):
        run(GrafanaBackend(transport=mock(handler)).verify(config, make_secrets()))


def test_grafana_discover_datasources() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/health":
            return json_response(FX["grafana_health_ok"])
        if request.url.path == "/api/datasources":
            return json_response(FX["grafana_datasources"])
        return json_response({}, status_code=404)

    config = make_config(base_url="http://grafana.lan:3000")
    records = drain(GrafanaBackend(transport=mock(handler)).discover(config, make_secrets()))
    # Instanz + 3 Datenquellen (eine ohne id wird übersprungen)
    assert [r.external_id for r in records] == ["grafana-instance", "datasource-1", "datasource-2", "datasource-3"]
    assert all(r.resource_type is ResourceType.DASHBOARD for r in records)


# -- Loki ---------------------------------------------------------------------


def test_loki_verify_available_no_api_version() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ready")

    config = make_config(base_url="http://loki.lan:3100")
    status = run(LokiBackend(transport=mock(handler)).verify(config, make_secrets()))
    assert status.state is AdapterState.OK
    assert status.api_version is None  # Loki liefert keine API-Version


def test_loki_not_ready_is_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    config = make_config(base_url="http://loki.lan:3100")
    with pytest.raises(AdapterApiError):
        run(LokiBackend(transport=mock(handler)).verify(config, make_secrets()))


def test_loki_capabilities_counts_labels() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/loki/api/v1/ready":
            return httpx.Response(200, text="ready")
        if request.url.path == "/loki/api/v1/labels":
            return json_response(FX["loki_labels"])
        return json_response({}, status_code=404)

    config = make_config(base_url="http://loki.lan:3100")
    caps = run(LokiBackend(transport=mock(handler)).capabilities(config, make_secrets()))
    assert caps.extra["labels"] == 4
    assert caps.extra["backend"] == "loki"


def test_loki_timeout() -> None:
    config = make_config(base_url="http://loki.lan:3100")
    from app.adapters.errors import AdapterTimeoutError

    with pytest.raises(AdapterTimeoutError):
        run(LokiBackend(transport=mock(timeout_handler(lambda: httpx.ReadTimeout("slow")))).verify(config, make_secrets()))


# -- Uptime Kuma ----------------------------------------------------------------


def test_uptime_kuma_verify_available() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(FX["uptime_status_up"])

    config = make_config(base_url="http://uptime.lan:3001")
    status = run(UptimeKumaBackend(transport=mock(handler)).verify(config, make_secrets()))
    assert status.state is AdapterState.OK


def test_uptime_kuma_verify_login_with_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/status":
            return json_response(FX["uptime_status_up"])
        if request.url.path == "/api/login":
            return json_response(FX["uptime_login_ok"])
        return json_response({}, status_code=404)

    config = make_config(base_url="http://uptime.lan:3001", secret_ref="UK_CREDS")
    status = run(
        UptimeKumaBackend(transport=mock(handler)).verify(config, make_secrets({"UK_CREDS": "admin:fixture-pass"}))
    )
    assert status.state is AdapterState.OK


def test_uptime_kuma_login_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/status":
            return json_response(FX["uptime_status_up"])
        if request.url.path == "/api/login":
            return json_response(FX["uptime_login_error"])

    config = make_config(base_url="http://uptime.lan:3001", secret_ref="UK_CREDS")
    with pytest.raises(AdapterAuthError):
        run(UptimeKumaBackend(transport=mock(handler)).verify(config, make_secrets({"UK_CREDS": "admin:falsch"})))


def test_uptime_kuma_discover_monitors_and_availability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/status":
            return json_response(FX["uptime_status_up"])
        if request.url.path == "/api/login":
            return json_response(FX["uptime_login_ok"])
        if request.url.path == "/api/monitor":
            return json_response(FX["uptime_monitors"])
        return json_response({}, status_code=404)

    config = make_config(base_url="http://uptime.lan:3001", secret_ref="UK_CREDS")
    backend = UptimeKumaBackend(transport=mock(handler))
    secrets = make_secrets({"UK_CREDS": "admin:fixture-pass"})
    records = drain(backend.discover(config, secrets))
    by_name = {r.name: r for r in records}
    assert by_name["Web (Fixture)"].status is ResourceStatus.HEALTHY
    assert by_name["Mail (Fixture)"].status is ResourceStatus.DOWN
    assert by_name["Paused (Fixture)"].status is ResourceStatus.UNKNOWN
    assert by_name["Web (Fixture)"].external_id == "monitor-11"

    services = run(backend.service_availability(config, secrets))
    by_service = {s.service: s for s in services}
    assert by_service["Web (Fixture)"].status is ResourceStatus.HEALTHY
    assert by_service["Mail (Fixture)"].detail == "down"


def test_uptime_kuma_down_state() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(FX["uptime_status_down"])

    config = make_config(base_url="http://uptime.lan:3001")
    status = run(UptimeKumaBackend(transport=mock(handler)).verify(config, make_secrets()))
    assert status.state is AdapterState.API_ERROR


# -- MonitoringAdapter (Engine): Backend-Auswahl -------------------------------


def test_engine_explicit_backend() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response({"status": "success", "data": {"version": "2.53.0"}})

    config = make_config(base_url="http://prometheus.lan:9090", extra={"backend": "prometheus"})
    adapter = MonitoringAdapter(transport=mock(handler))
    status = run(adapter.verify(config, make_secrets()))
    assert status.state is AdapterState.OK
    caps = run(adapter.capabilities(config, make_secrets()))
    assert caps.extra["backend"] == "prometheus"


def test_engine_unknown_backend_is_config_error() -> None:
    config = make_config(base_url="http://x.lan", extra={"backend": "influxdb"})
    adapter = MonitoringAdapter(transport=mock(lambda request: json_response({})))
    with pytest.raises(AdapterConfigError):
        run(adapter.verify(config, make_secrets()))


def test_engine_autodetect_prometheus() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/status/buildinfo":
            return json_response({"status": "success", "data": {"version": "2.50.0"}})
        return json_response({}, status_code=404)

    config = make_config(base_url="http://prometheus.lan:9090")
    assert run(MonitoringAdapter(transport=mock(handler)).detect(config, make_secrets())) == "prometheus"


def test_engine_autodetect_uptime_kuma() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/status":
            return json_response({"status": "UP"})
        return json_response({}, status_code=404)

    config = make_config(base_url="http://uptime.lan:3001")
    assert run(MonitoringAdapter(transport=mock(handler)).detect(config, make_secrets())) == "uptime_kuma"


def test_engine_autodetect_grafana() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/health":
            return json_response(FX["grafana_health_ok"])
        return json_response({}, status_code=404)

    config = make_config(base_url="http://grafana.lan:3000")
    assert run(MonitoringAdapter(transport=mock(handler)).detect(config, make_secrets())) == "grafana"


def test_engine_autodetect_loki() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/loki/api/v1/labels":
            return json_response(FX["loki_labels"])
        return json_response({}, status_code=404)

    config = make_config(base_url="http://loki.lan:3100")
    assert run(MonitoringAdapter(transport=mock(handler)).detect(config, make_secrets())) == "loki"


def test_engine_autodetect_no_match_is_config_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response({"unbekannt": True})

    config = make_config(base_url="http://mystery.lan")
    with pytest.raises(AdapterConfigError):
        run(MonitoringAdapter(transport=mock(handler)).detect(config, make_secrets()))


def test_engine_delegates_discover_and_collect() -> None:
    """Engine delegiert Discover/Collect ans gewaehlte Backend."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/label/instance/values":
            return json_response({"status": "success", "data": ["h.lan:9100"]})
        if request.url.path == "/api/v1/query":
            return json_response({"status": "success", "data": {"resultType": "vector", "result": []}})
        return json_response({"status": "success", "data": {"version": "2.53.0"}})

    config = make_config(base_url="http://prometheus.lan:9090", extra={"backend": "prometheus"})
    adapter = MonitoringAdapter(transport=mock(handler))
    records = drain(adapter.discover(config, make_secrets()))
    assert [r.external_id for r in records] == ["h.lan:9100"]
    record = run(adapter.collect(config, make_secrets(), ResourceType.HOST, "h.lan:9100"))
    assert record.metrics == {}
