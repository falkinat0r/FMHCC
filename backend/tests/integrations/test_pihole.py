"""Pi-hole-Adapter-Tests (fixture-basiert, Agent 4, R1).

Szenarien: v6 REST (available/auth/collect), v5 api.php (available/
collect/FTL-down/auth-falsch), Blocking-Status 'failed' => Metrik wird
nicht erfunden, Timeout, not_configured, unterschiedliche API-Versionen,
zwei parallele Instanzen (mehrere Integrationen).
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
from app.integrations.pihole.adapter import PiholeAdapter
from app.models.resources import ResourceType
from tests.integrations.conftest import (
    drain,
    json_response,
    load_fixture,
    make_config,
    make_secrets,
    run,
    timeout_handler,
)

FX = load_fixture("pihole.json")


def v6_routes(auth_ok: bool = True, auth_required: bool = False) -> Callable[[httpx.Request], httpx.Response]:
    """v6-Routen: Erkennung via /api/info/login, Auth via /api/auth."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/info/login":
            return json_response(FX["v6_login_info"])
        if path == "/api/auth" and request.method == "GET":
            if auth_required:
                return json_response({"valid": False, "reason": "authentication is required"})
            return json_response(FX["v6_auth_noauth"])
        if path == "/api/auth" and request.method == "POST":
            if not auth_ok:
                return json_response({"success": False}, status_code=401)
            return json_response(FX["v6_auth_login"])
        if path == "/api/dns/blocking":
            return json_response(FX["v6_blocking_enabled"])
        if path == "/api/stats/summary":
            return json_response(FX["v6_summary"])
        return json_response({"error": "unroutet"}, status_code=404)

    return handler


def v5_routes(
    summary: dict | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """v5-Routen: Erkennung via /admin/api.php?versions, Daten via ?summaryRaw."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/info/login":
            return json_response({"error": "not found"}, status_code=404)
        if path == "/admin/api.php":
            params = request.url.params
            if "versions" in params:
                return json_response(FX["v5_versions"])
            if "summaryRaw" in params:
                return json_response(summary if summary is not None else FX["v5_summary"])
        return json_response({"error": "unroutet"}, status_code=404)

    return handler


def adapter(handler: Callable[[httpx.Request], httpx.Response]) -> PiholeAdapter:
    return PiholeAdapter(transport=httpx.MockTransport(handler))


def test_v6_verify_available_without_auth() -> None:
    config = make_config(base_url="http://pihole.lan:8080")
    status = run(adapter(v6_routes()).verify(config, make_secrets()))
    assert status.state is AdapterState.OK
    assert "v6" in status.message


def test_v6_verify_with_session_auth() -> None:
    """v6 mit Passwort: POST /api/auth liefert Session (SID)."""
    config = make_config(base_url="http://pihole.lan:8080", secret_ref="PIHOLE_PW")
    status = run(adapter(v6_routes()).verify(config, make_secrets({"PIHOLE_PW": "fixture-pass"})))
    assert status.state is AdapterState.OK


def test_v6_verify_wrong_password() -> None:
    config = make_config(base_url="http://pihole.lan:8080", secret_ref="PIHOLE_PW")
    with pytest.raises(AdapterAuthError):
        run(adapter(v6_routes(auth_ok=False)).verify(config, make_secrets({"PIHOLE_PW": "falsch"})))


def test_v6_verify_password_required_but_missing() -> None:
    """Instanz braucht Passwort, aber kein Secret konfiguriert => auth_failed."""
    config = make_config(base_url="http://pihole.lan:8080")
    with pytest.raises(AdapterAuthError):
        run(adapter(v6_routes(auth_required=True)).verify(config, make_secrets()))


def test_v6_collect_summary_metrics() -> None:
    config = make_config(base_url="http://pihole.lan:8080")
    record = run(
        adapter(v6_routes()).collect(config, make_secrets(), ResourceType.DNS_STATS, "summary")
    )
    metrics = record.metrics
    assert metrics["dns_queries"].value == 123456
    assert metrics["dns_blocked"].value == 678
    assert metrics["blocked_percent"].value == 0.55
    assert metrics["blocking_enabled"].value == 1.0
    assert metrics["blocked_domains"].value == 45210


def test_v6_blocking_failed_is_not_fabricated() -> None:
    """Blocking-Status 'failed' => Metrik wird weggelassen, nicht erfunden."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/info/login":
            return json_response(FX["v6_login_info"])
        if request.url.path == "/api/auth":
            return json_response(FX["v6_auth_noauth"])  # auth-freie Instanz
        if request.url.path == "/api/dns/blocking":
            return json_response(FX["v6_blocking_failed"])
        if request.url.path == "/api/stats/summary":
            return json_response(FX["v6_summary"])
        return json_response({"error": "unroutet"}, status_code=404)

    config = make_config(base_url="http://pihole.lan:8080")
    record = run(adapter(handler).collect(config, make_secrets(), ResourceType.DNS_STATS, "summary"))
    assert "blocking_enabled" not in record.metrics
    assert record.metrics["dns_queries"].value == 123456  # andere Metriken bleiben


def test_v5_verify_available() -> None:
    config = make_config(base_url="http://pihole5.lan:80")
    status = run(adapter(v5_routes()).verify(config, make_secrets()))
    assert status.state is AdapterState.OK
    assert "v5" in status.message
    assert status.api_version == "5.21.2"


def test_v5_collect_with_pwhash() -> None:
    config = make_config(base_url="http://pihole5.lan:80", secret_ref="PIHOLE_PWHASH")
    record = run(
        adapter(v5_routes()).collect(config, make_secrets({"PIHOLE_PWHASH": "sha256-fixture"}), ResourceType.DNS_STATS, "summary")
    )
    metrics = record.metrics
    assert metrics["dns_queries"].value == 98765
    assert metrics["dns_blocked"].value == 234
    assert metrics["blocked_percent"].value == 0.24
    assert metrics["blocking_enabled"].value == 1.0


def test_v5_ftl_down_is_api_error() -> None:
    config = make_config(base_url="http://pihole5.lan:80")
    with pytest.raises(AdapterApiError):
        run(adapter(v5_routes(summary=FX["v5_ftl_down"])).collect(config, make_secrets(), ResourceType.DNS_STATS, "summary"))


def test_v5_auth_false_is_auth_error() -> None:
    config = make_config(base_url="http://pihole5.lan:80", secret_ref="PIHOLE_PWHASH")
    with pytest.raises(AdapterAuthError):
        run(
            adapter(v5_routes(summary=FX["v5_auth_required"])).collect(
                config, make_secrets({"PIHOLE_PWHASH": "falsch"}), ResourceType.DNS_STATS, "summary"
            )
        )


def test_unknown_api_is_version_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response({"error": "no"}, status_code=404)

    config = make_config(base_url="http://pihole.lan:8080")
    with pytest.raises(AdapterVersionError):
        run(adapter(handler).verify(config, make_secrets()))


def test_not_configured() -> None:
    config = make_config()
    with pytest.raises(AdapterConfigError):
        run(adapter(v6_routes()).verify(config, make_secrets()))


def test_timeout() -> None:
    config = make_config(base_url="http://pihole.lan:8080")
    with pytest.raises(AdapterTimeoutError):
        run(adapter(timeout_handler(lambda: httpx.ReadTimeout("slow"))).verify(config, make_secrets()))


def test_wrong_resource_type_is_config_error() -> None:
    config = make_config(base_url="http://pihole.lan:8080")
    with pytest.raises(AdapterConfigError):
        run(adapter(v6_routes()).collect(config, make_secrets(), ResourceType.POOL, "tank"))


def test_multiple_instances_are_independent() -> None:
    """Mehrere Instanzen = mehrere Integrationen; Adapter je Instanz.

    Instanz A läuft ohne Auth (v6), Instanz B mit Auth (v6); beide
    liefern eigene Werte — keine Kreuzverschmutzung.
    """
    config_a = make_config(base_url="http://pihole-a.lan")
    config_b = make_config(base_url="http://pihole-b.lan", secret_ref="PIHOLE_PW_B")
    adapter_a = adapter(v6_routes())
    adapter_b = adapter(v6_routes())
    status_a = run(adapter_a.verify(config_a, make_secrets()))
    status_b = run(adapter_b.verify(config_b, make_secrets({"PIHOLE_PW_B": "fixture-b"})))
    assert status_a.state is AdapterState.OK
    assert status_b.state is AdapterState.OK
    record_a = run(adapter_a.collect(config_a, make_secrets(), ResourceType.DNS_STATS, "summary"))
    record_b = run(adapter_b.collect(config_b, make_secrets({"PIHOLE_PW_B": "fixture-b"}), ResourceType.DNS_STATS, "summary"))
    assert record_a.metrics["dns_queries"].value == 123456
    assert record_b.metrics["dns_queries"].value == 123456
    # Entkoppelt: A ohne, B mit Auth (verschiedene Integrationen)
    assert config_a.secret_ref is None
    assert config_b.secret_ref == "PIHOLE_PW_B"


def test_discover_yields_dns_stats_resource() -> None:
    config = make_config(base_url="http://pihole.lan:8080")
    records = drain(adapter(v6_routes()).discover(config, make_secrets()))
    assert len(records) == 1
    assert records[0].resource_type is ResourceType.DNS_STATS
    assert records[0].external_id == "summary"
