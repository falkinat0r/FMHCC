"""Docker-Adapter-Tests (fixture-basiert, Agent 4, R1).

Szenarien: Zugriffs-Modell-Sicherheit (plain TCP reject, Loopback,
Unix-Socket, mTLS), Verify, Discover (Host + Container mit Compose-
Labels + State-Mapping), Collect (stats, ID-Validierung), Auth-Fehler,
Timeout, not_configured.
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
from app.integrations.docker.adapter import DockerAdapter
from app.integrations.docker.security import DockerAccess, resolve_docker_access
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

FX = load_fixture("docker.json")


def engine_handler() -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/version":
            return json_response(FX["version"])
        if path == "/info":
            return json_response(FX["info"])
        if path == "/containers/json":
            return json_response(FX["containers"])
        if path == "/images/json":
            return json_response(FX["images"])
        if path.startswith("/containers/"):
            if path.endswith("/stats"):
                return json_response(FX["stats"])
            return json_response({"error": "unroutet"}, status_code=404)
        return json_response({"error": "unroutet"}, status_code=404)

    return handler


def adapter(handler: Callable[[httpx.Request], httpx.Response] | None = None) -> DockerAdapter:
    transport = httpx.MockTransport(handler) if handler is not None else httpx.MockTransport(engine_handler())
    return DockerAdapter(transport=transport)


# -- Sicherheitspolitik (ohne Netzwerk) ------------------------------------


def test_plain_tcp_to_remote_is_rejected() -> None:
    config = make_config(base_url="http://192.168.1.50:2375")
    with pytest.raises(AdapterConfigError):
        resolve_docker_access(config)


def test_plain_tcp_loopback_allowed_but_dangerous() -> None:
    config = make_config(base_url="http://127.0.0.1:2375")
    access = resolve_docker_access(config)
    assert access.mode == "tcp_loopback"
    assert any("hohes Risiko" in note for note in access.security_notes)


def test_https_remote_with_client_cert() -> None:
    config = make_config(
        base_url="https://docker.lan:2376",
        extra={"docker_ca": "/etc/hcc/ca.pem", "docker_cert": "/etc/hcc/cert.pem", "docker_key": "/etc/hcc/key.pem"},
    )
    access = resolve_docker_access(config)
    assert isinstance(access, DockerAccess)
    assert access.mode == "tcp_tls"
    # Transport wird lazig gebaut (keine Dateizugriffe bei der Policy-Pruefung)
    assert access.ca == "/etc/hcc/ca.pem"
    assert access.cert == "/etc/hcc/cert.pem"
    assert access.key == "/etc/hcc/key.pem"


def test_cert_without_key_is_config_error() -> None:
    config = make_config(base_url="https://docker.lan:2376", extra={"docker_cert": "/etc/hcc/cert.pem"})
    with pytest.raises(AdapterConfigError):
        resolve_docker_access(config)


def test_unix_socket_requires_absolute_path() -> None:
    config = make_config(base_url=None, extra={"docker_socket": "relative.sock"})
    with pytest.raises(AdapterConfigError):
        resolve_docker_access(config)
    config = make_config(base_url=None, extra={"docker_socket": "/var/run/docker.sock"})
    access = resolve_docker_access(config)
    assert access.mode == "unix_socket"
    assert access.uds_path == "/var/run/docker.sock"


def test_no_access_configured_is_not_configured() -> None:
    with pytest.raises(AdapterConfigError):
        resolve_docker_access(make_config())


# -- Adapter-Verhalten -------------------------------------------------------


def test_verify_available() -> None:
    config = make_config(base_url="http://127.0.0.1:2375", extra={"docker_socket": "/var/run/docker.sock"})
    status = run(adapter().verify(config, make_secrets()))
    assert status.state is AdapterState.OK
    assert status.api_version == "1.47"


def test_verify_timeout() -> None:
    config = make_config(base_url="http://127.0.0.1:2375", extra={"docker_socket": "/var/run/docker.sock"})
    with pytest.raises(AdapterTimeoutError):
        run(adapter(timeout_handler(lambda: httpx.ReadTimeout("slow"))).verify(config, make_secrets()))


def test_verify_auth_failed() -> None:
    config = make_config(base_url="http://127.0.0.1:2375", extra={"docker_socket": "/var/run/docker.sock"})
    with pytest.raises(AdapterAuthError):
        run(adapter(lambda request: json_response({"message": "401 unauthorized"}, status_code=401)).verify(config, make_secrets()))


def test_discover_host_containers_images() -> None:
    config = make_config(base_url="http://127.0.0.1:2375", extra={"docker_socket": "/var/run/docker.sock"})
    records = drain(adapter().discover(config, make_secrets()))
    by_type = {}
    for record in records:
        by_type.setdefault(record.resource_type, []).append(record)
    hosts = by_type[ResourceType.HOST]
    containers = by_type[ResourceType.CONTAINER]
    assert len(hosts) == 1
    assert hosts[0].name == "fixture-docker-host"
    assert hosts[0].payload["images_count"] == 2
    assert len(containers) == 3
    running = next(c for c in containers if c.external_id == "a1b2c3d4e5f607182930")
    assert running.status is ResourceStatus.HEALTHY
    assert running.payload["compose_project"] == "hcc"
    assert running.payload["compose_service"] == "backend"
    exited = next(c for c in containers if c.external_id == "b2c3d4e5f60718293041")
    assert exited.status is ResourceStatus.DOWN
    paused = next(c for c in containers if c.external_id == "c3d4e5f6071829304152")
    assert paused.status is ResourceStatus.DEGRADED


def test_collect_container_stats() -> None:
    config = make_config(base_url="http://127.0.0.1:2375", extra={"docker_socket": "/var/run/docker.sock"})
    record = run(adapter().collect(config, make_secrets(), ResourceType.CONTAINER, "a1b2c3d4e5f607182930"))
    metrics = record.metrics
    # CPU: (1125000-1000000)/(8000000-7000000)*2*100 = 25.0
    assert metrics["cpu_percent"].unit == "percent"
    assert 24.9 <= metrics["cpu_percent"].value <= 25.1
    assert metrics["memory_usage"].value == 536870912
    assert metrics["memory_limit"].value == 2147483648
    assert metrics["network_rx"].value == 1000
    assert metrics["network_tx"].value == 2000
    # blkio ist format-chaotisch => bewusst keine Metrik
    assert "block_read" not in metrics


def test_collect_rejects_invalid_container_id() -> None:
    config = make_config(base_url="http://127.0.0.1:2375", extra={"docker_socket": "/var/run/docker.sock"})
    with pytest.raises(AdapterConfigError):
        run(adapter().collect(config, make_secrets(), ResourceType.CONTAINER, "abc/../../etc"))
    with pytest.raises(AdapterConfigError):
        run(adapter().collect(config, make_secrets(), ResourceType.CONTAINER, "zu_kurz"))


def test_collect_wrong_resource_type() -> None:
    config = make_config(base_url="http://127.0.0.1:2375", extra={"docker_socket": "/var/run/docker.sock"})
    with pytest.raises(AdapterConfigError):
        run(adapter().collect(config, make_secrets(), ResourceType.HOST, "host"))


def test_capabilities_includes_security_mode() -> None:
    config = make_config(base_url="http://127.0.0.1:2375", extra={"docker_socket": "/var/run/docker.sock"})
    caps = run(adapter().capabilities(config, make_secrets()))
    assert caps.extra["mode"] == "unix_socket"
    assert caps.extra["engine"] == "Docker Engine Community"
    assert caps.api_version == "1.47"
