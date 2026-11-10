"""Prometheus-Backend-Tests (fixture-basiert, Agent 4, R1).

Szenarien: Service available, not_configured, Auth-Fehler, Timeout,
leere Metrik-Antworten, kaputte Metrik-Werte (NaN/garbage), API-Error-
Payload, Label-Validierung, Discover, Historical mit Label-Filter,
Alertmanager-Alerts.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.adapters.errors import (
    AdapterApiError,
    AdapterAuthError,
    AdapterConfigError,
    AdapterError,
    AdapterState,
    AdapterTimeoutError,
)
from app.integrations.monitoring.base import TimeRange
from app.integrations.monitoring.prometheus import (
    PrometheusBackend,
    validate_label_value,
)
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

FX = load_fixture("prometheus.json")


def routes(handler: Callable[[httpx.Request], httpx.Response] | None = None) -> Callable[[httpx.Request], httpx.Response]:
    """Standard-Routen (buildinfo + query + label values); override per Query moeglich."""

    def handler_default(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/status/buildinfo":
            return json_response(FX["buildinfo"])
        if request.url.path == "/api/v1/label/instance/values":
            return json_response(FX["instances"])
        if request.url.path == "/api/v1/query":
            query = request.url.params.get("query", "")
            if "idle" in query:  # cpu_percent-Template
                return json_response(FX["cpu_instant"])
            if query == "up":
                return json_response(FX["up"])
            if query.startswith("100 * (1 -"):  # disk/memory-Template
                return json_response(FX["empty_query"])
            return json_response(FX["memory_available"])
        if request.url.path == "/api/v1/query_range":
            return json_response(FX["cpu_range"])
        if handler is not None:
            return handler(request)
        return json_response({"status": "error", "error": "unroutet"}, status_code=404)

    return handler_default


def backend(routes_fn: Callable[[httpx.Request], httpx.Response]) -> PrometheusBackend:
    import httpx as _httpx

    return PrometheusBackend(transport=_httpx.MockTransport(routes_fn))


def test_verify_available() -> None:
    config = make_config(base_url="http://prometheus.lan:9090")
    status = run(backend(routes()).verify(config, make_secrets()))
    assert status.state is AdapterState.OK
    assert status.api_version == "2.53.0"


def test_verify_not_configured() -> None:
    config = make_config()
    with pytest.raises(AdapterConfigError):
        run(backend(routes()).verify(config, make_secrets()))


def test_verify_timeout() -> None:
    config = make_config(base_url="http://prometheus.lan:9090")
    with pytest.raises(AdapterTimeoutError):
        run(backend(timeout_handler(lambda: httpx.ReadTimeout("slow"))).verify(config, make_secrets()))


def test_verify_auth_failed() -> None:
    config = make_config(base_url="http://prometheus.lan:9090", secret_ref="PROM_SECRET")
    with pytest.raises(AdapterAuthError):
        run(
            backend(lambda request: json_response({"error": "unauthorized"}, status_code=401)).verify(
                config, make_secrets({"PROM_SECRET": "fixture-basic-user:fixture-pass"})
            )
        )


def test_verify_api_error_payload() -> None:
    config = make_config(base_url="http://prometheus.lan:9090")
    with pytest.raises(AdapterApiError) as exc_info:
        run(backend(lambda request: json_response(FX["error"])).verify(config, make_secrets()))
    assert exc_info.value.state is AdapterState.API_ERROR


def test_discover_instance_labels() -> None:
    config = make_config(base_url="http://prometheus.lan:9090")
    records = drain(backend(routes()).discover(config, make_secrets()))
    assert [r.external_id for r in records] == ["host1.lan:9100", "host2.lan:9100"]
    assert all(r.resource_type is ResourceType.HOST for r in records)


def test_host_availability_from_up() -> None:
    config = make_config(base_url="http://prometheus.lan:9090")
    hosts = run(backend(routes()).host_availability(config, make_secrets()))
    by_id = {h.external_id: h for h in hosts}
    assert by_id["host1.lan:9100"].status is ResourceStatus.HEALTHY
    assert by_id["host2.lan:9100"].status is ResourceStatus.DOWN
    assert by_id["host2.lan:9100"].detail == "up=0"


def test_current_metrics_filters_by_instance_and_skips_bad_values() -> None:
    """Leere Antwort + NaN + Label-Filter: nur valide, zugehoerige Werte."""
    config = make_config(base_url="http://prometheus.lan:9090")
    record = run(
        backend(routes()).current_metrics(config, make_secrets(), ResourceType.HOST, "host1.lan:9100")
    )
    # up (1) und memory_available (8589934592) vorhanden; 'garbage'-Wert wird
    # client-seitig verworfen (erste valide Series pro Template gewinnt).
    assert record.metrics["up"].value == 1.0
    assert record.metrics["up"].unit == "ratio"
    assert record.metrics["memory_available_bytes"].value == 8589934592
    assert record.metrics["memory_available_bytes"].unit == "bytes"
    assert record.metrics["cpu_percent"].value == 12.5


def test_current_metrics_empty_response() -> None:
    """Leere Metrik-Antwort => leeres metrics-Dict (keine erfundenen Werte)."""
    config = make_config(base_url="http://prometheus.lan:9090")
    record = run(
        backend(lambda request: json_response(FX["empty_query"])).current_metrics(
            config, make_secrets(), ResourceType.HOST, "host1.lan:9100"
        )
    )
    assert record.metrics == {}


def test_current_metrics_label_value_rejects_injection() -> None:
    config = make_config(base_url="http://prometheus.lan:9090")
    with pytest.raises(AdapterConfigError):
        run(backend(routes()).current_metrics(config, make_secrets(), ResourceType.HOST, "../etc/passwd"))


def test_current_metrics_unknown_resource_type() -> None:
    config = make_config(base_url="http://prometheus.lan:9090")
    with pytest.raises(AdapterError) as exc_info:
        run(backend(routes()).current_metrics(config, make_secrets(), ResourceType.POOL, "tank"))
    assert exc_info.value.state is AdapterState.NOT_IMPLEMENTED


def test_historical_metrics_label_filter_and_nan_skip() -> None:
    config = make_config(base_url="http://prometheus.lan:9090")
    series = run(
        backend(routes()).historical_metrics(
            config,
            make_secrets(),
            metric="cpu_percent",
            labels={"instance": "host1.lan:9100"},
            range=TimeRange.ONE_HOUR,
        )
    )
    assert len(series) == 1
    assert series[0].labels["instance"] == "host1.lan:9100"
    # NaN-Punkt wird verworfen, valide Punkte bleiben
    assert [p.value for p in series[0].points] == [12.5, 13.1]
    assert all(p.unit == "percent" for p in series[0].points)


def test_historical_metrics_unknown_template() -> None:
    config = make_config(base_url="http://prometheus.lan:9090")
    with pytest.raises(AdapterConfigError):
        run(
            backend(routes()).historical_metrics(
                config, make_secrets(), metric="free-form-promql", labels={}, range=TimeRange.ONE_HOUR
            )
        )


def test_alertmanager_alerts_normalized() -> None:
    config = make_config(
        base_url="http://prometheus.lan:9090", extra={"alertmanager_url": "http://am.lan:9093"}
    )
    am_routes = {"/api/v2/alerts": load_fixture("alertmanager.json")["alerts"]}
    import httpx as _httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "am.lan":
            return json_response(am_routes[request.url.path])
        return json_response(FX["buildinfo"])

    backend_ = PrometheusBackend(transport=_httpx.MockTransport(handler))
    alerts = drain(backend_.alerts(config, make_secrets()))
    assert [a.name for a in alerts] == ["HostDown", "HighCpu"]
    assert alerts[0].severity.value == "critical"
    assert alerts[0].resource is not None and alerts[0].resource.external_id == "host2.lan:9100"
    assert alerts[0].labels["instance"] == "host2.lan:9100"
    assert alerts[1].severity.value == "warning"


def test_alerts_without_alertmanager_are_empty() -> None:
    config = make_config(base_url="http://prometheus.lan:9090")
    alerts = drain(backend(routes()).alerts(config, make_secrets()))
    assert alerts == []


def test_label_value_whitelist() -> None:
    with pytest.raises(AdapterConfigError):
        validate_label_value('a"b')
    validate_label_value("host1.lan:9100")  # valide Werte bleiben erlaubt
