"""Compute-Aktions-Tests (Agent 3, R1).

Deckung: Endpoint-Mapping, Node-Aufloesung (Cluster-Resources + Fallback),
ActionJob-Idempotenz, RBAC (viewer 403), Bestaetigung (422), Fehlermauerung
ins Job-Modell (FAILED + error_state), Audit-Events, asynchrone UPID-Antwort.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select

from app.adapters.base import AdapterState
from app.adapters.errors import AdapterConfigError, AdapterError
from app.errors import ApiError
from app.integrations.proxmox.actions import (
    action_endpoint,
    execute_compute_action,
    require_actions_run,
    resolve_target,
    submit_action_job,
)
from app.integrations.proxmox.adapter import ProxmoxAdapter
from app.models.action_jobs import ActionJob, ActionType, JobStatus
from app.models.users import Role, User
from tests.proxmox.conftest import (
    audit_actions,
    client_request,
    make_config,
    make_integration,
    make_secrets,
    run,
)
from tests.proxmox.fixtures import cluster_scenario, standalone_scenario

# ------------------------------------------------------------------ helpers


def _user(db, role: Role, username: str) -> User:
    user = User(username=username, role=role, password_hash="test-hash-keines-echtes-secret", is_active=True)
    db.add(user)
    db.flush()
    return user


def test_action_endpoint_mapping() -> None:
    assert action_endpoint("qemu", "start", "pve1", "101") == "/nodes/pve1/qemu/101/status/start"
    # Shutdown/Reboot sind ACPI-sanft (status/shutdown, status/restart)
    assert action_endpoint("qemu", "shutdown", "pve1", "101") == "/nodes/pve1/qemu/101/status/shutdown"
    assert action_endpoint("qemu", "reboot", "pve1", "101") == "/nodes/pve1/qemu/101/status/restart"
    # LXC: sanfter Stop OHNE --force, kein /status/stop
    assert action_endpoint("lxc", "start", "pve1", "201") == "/nodes/pve1/lxc/201/start"
    assert action_endpoint("lxc", "shutdown", "pve1", "201") == "/nodes/pve1/lxc/201/stop"
    assert action_endpoint("lxc", "reboot", "pve1", "201") == "/nodes/pve1/lxc/201/restart"
    # Erzwungene Stopps / Loeschungen sind bewusst NICHT implementiert
    assert action_endpoint("qemu", "stop", "pve1", "101") is None
    assert action_endpoint("qemu", "destroy", "pve1", "101") is None


def test_resolve_target_via_cluster_resources() -> None:
    server = standalone_scenario()

    async def _scenario(client):
        vm = await resolve_target(client, "101")
        ct = await resolve_target(client, "201")
        return vm, ct

    vm, ct = client_request(server, _scenario)
    assert vm == ("pve1", "qemu")
    assert ct == ("pve1", "lxc")


def test_resolve_target_not_found_raises_404() -> None:
    server = standalone_scenario()
    with pytest.raises(AdapterError) as exc_info:
        client_request(server, lambda client: resolve_target(client, "999"))
    assert exc_info.value.state is AdapterState.API_ERROR


def test_resolve_target_fallback_probes_nodes_without_cluster_resources() -> None:
    server = standalone_scenario()
    server.forbidden_paths = {"/cluster/resources"}

    result = client_request(server, lambda client: resolve_target(client, "102"))
    assert result == ("pve1", "qemu")
    # Fallback-Abfrage pro Node
    assert "/nodes/pve1/qemu/102" in server.paths()


def test_submit_action_job_creates_and_reuses(db) -> None:
    integration = make_integration(db)
    user = _user(db, Role.OPERATOR, "op-job")

    job1, created1 = submit_action_job(
        db,
        integration=integration,
        action=ActionType.START,
        external_resource_id="101",
        requested_by=user.id,
        idempotency_key="k-101",
    )
    assert created1 is True
    assert job1.status is JobStatus.PENDING

    job2, created2 = submit_action_job(
        db,
        integration=integration,
        action=ActionType.START,
        external_resource_id="101",
        requested_by=user.id,
        idempotency_key="k-101",
    )
    assert created2 is False
    assert job2.id == job1.id

    job3, created3 = submit_action_job(
        db,
        integration=integration,
        action=ActionType.START,
        external_resource_id="101",
        requested_by=user.id,
        idempotency_key="k-101-andere",
    )
    assert created3 is True
    assert job3.id != job1.id


def test_require_actions_run_enforces_role(db) -> None:
    operator = _user(db, Role.OPERATOR, "op-rbac")
    viewer = _user(db, Role.VIEWER, "viewer-rbac")
    admin = _user(db, Role.ADMIN, "admin-rbac")
    require_actions_run(operator)
    require_actions_run(admin)
    with pytest.raises(ApiError) as exc_info:
        require_actions_run(viewer)
    assert exc_info.value.status_code == 403


# ----------------------------------------------------------------- executor


def _execute(db, server, user, *, action, external_id, **kwargs):
    """Fuehrt eine Aktion aus; ``act()`` baut selbst einen Client (globaler Test-Transport)."""
    from app.integrations.proxmox.client import set_test_transport

    set_test_transport(httpx.MockTransport(server.handle))
    try:
        return run(
            execute_compute_action(
                db,
                adapter=ProxmoxAdapter(),
                config=make_config(),
                secrets=make_secrets(),
                integration=make_integration(db),
                user=user,
                action=action,
                external_id=external_id,
                **kwargs,
            )
        )
    finally:
        set_test_transport(None)


def test_execute_start_succeeded_with_audit(db) -> None:
    server = standalone_scenario()
    user = _user(db, Role.OPERATOR, "op-start")

    job = _execute(db, server, user, action=ActionType.START, external_id="101", idempotency_key="k-start-101")

    assert job.status is JobStatus.SUCCEEDED
    assert job.started_at is not None
    assert job.finished_at is not None
    # Genauer Proxmox-Endpoint (start auf pve1), keine Uebergriffe
    assert server.action_log == ["/nodes/pve1/qemu/101/status/start"]
    # Asynchrone Task-Antwort (UPID) wird dokumentiert, nicht simuliert
    assert "UPID:pve1" in job.details["task"]
    assert job.details["adapter_state"] == AdapterState.OK.value

    assert "actions.compute.start" in audit_actions(db)
    assert "actions.compute.start.accepted" in audit_actions(db)


def test_execute_shutdown_uses_acpi_endpoint(db) -> None:
    server = standalone_scenario()
    user = _user(db, Role.OPERATOR, "op-shutdown")
    job = _execute(db, server, user, action=ActionType.SHUTDOWN, external_id="102", idempotency_key="k-sh-102")
    assert job.status is JobStatus.SUCCEEDED
    assert server.action_log == ["/nodes/pve1/qemu/102/status/shutdown"]


def test_execute_lxc_shutdown_uses_graceful_stop(db) -> None:
    server = standalone_scenario()
    user = _user(db, Role.OPERATOR, "op-lxc")
    job = _execute(db, server, user, action=ActionType.SHUTDOWN, external_id="201", idempotency_key="k-lxc-201")
    assert job.status is JobStatus.SUCCEEDED
    assert server.action_log == ["/nodes/pve1/lxc/201/stop"]


def test_execute_reboot_on_cluster_node(db) -> None:
    server = cluster_scenario()
    user = _user(db, Role.OPERATOR, "op-reboot")
    job = _execute(db, server, user, action=ActionType.REBOOT, external_id="104", idempotency_key="k-reb-104")
    assert job.status is JobStatus.SUCCEEDED
    assert server.action_log == ["/nodes/pve2/qemu/104/status/restart"]
    assert "UPID:pve2" in job.details["task"]


def test_execute_adapter_error_marks_job_failed(db) -> None:
    server = standalone_scenario()
    server.action_errors = {"qemu:pve1:101:shutdown": 500}
    user = _user(db, Role.OPERATOR, "op-fail")

    job = _execute(db, server, user, action=ActionType.SHUTDOWN, external_id="101", idempotency_key="k-fail-101")

    assert job.status is JobStatus.FAILED
    assert job.details["error_state"] == AdapterState.API_ERROR.value
    assert "500" in job.details["error"]
    assert "actions.compute.shutdown.failed" in audit_actions(db)
    assert "actions.compute.shutdown.accepted" not in audit_actions(db)


def test_execute_unreachable_marks_job_failed(db) -> None:
    server = standalone_scenario()
    server.network_error = "unreachable"
    user = _user(db, Role.OPERATOR, "op-unreach")

    job = _execute(db, server, user, action=ActionType.START, external_id="101", idempotency_key="k-unreach-101")

    assert job.status is JobStatus.FAILED
    assert job.details["error_state"] == AdapterState.UNREACHABLE.value
    # Adapter-Fehler wurde NICHT an den Aufrufer geworfen (Job traegt den Fehler)
    assert "actions.compute.start.failed" in audit_actions(db)


def test_execute_idempotent_replay_does_not_repeat_action(db) -> None:
    server = standalone_scenario()
    user = _user(db, Role.OPERATOR, "op-replay")

    job1 = _execute(db, server, user, action=ActionType.START, external_id="101", idempotency_key="k-replay")
    job2 = _execute(db, server, user, action=ActionType.START, external_id="101", idempotency_key="k-replay")

    assert job1.id == job2.id
    assert job2.status is JobStatus.SUCCEEDED
    # Die Proxmox-API wurde exakt EINMAL geschriebenen
    assert server.action_log == ["/nodes/pve1/qemu/101/status/start"]
    assert "actions.compute.replay" in audit_actions(db)


def test_execute_requires_confirmation(db) -> None:
    server = standalone_scenario()
    user = _user(db, Role.OPERATOR, "op-noconfirm")

    with pytest.raises(ApiError) as exc_info:
        _execute(db, server, user, action=ActionType.START, external_id="101", confirmed=False)
    assert exc_info.value.status_code == 422
    assert server.action_log == []
    assert db.scalar(select(func.count()).select_from(ActionJob)) == 0


def test_execute_viewer_is_denied(db) -> None:
    server = standalone_scenario()
    viewer = _user(db, Role.VIEWER, "viewer-action")

    with pytest.raises(ApiError) as exc_info:
        _execute(db, server, viewer, action=ActionType.START, external_id="101")
    assert exc_info.value.status_code == 403
    assert server.action_log == []
    assert db.scalar(select(func.count()).select_from(ActionJob)) == 0
    # Kein Audit-Event: die Aktion wurde serverseitig abgelehnt
    assert audit_actions(db) == []


def test_task_upid_is_pollable() -> None:
    """Die async Task-Antwort (UPID) ist ueber /nodes/{n}/tasks/{upid} abrufbar."""
    server = standalone_scenario()

    async def _scenario(client):
        upid = await client.post("/nodes/pve1/qemu/101/status/start")
        task = await client.get(f"/nodes/pve1/tasks/{upid}")
        return upid, task

    upid, task = client_request(server, _scenario)
    assert isinstance(upid, str)
    assert upid.startswith("UPID:pve1:")
    assert task == {"status": "stopped", "exitstatus": "OK"}


# ------------------------------------------------------------- adapter.act guards


def test_act_requires_confirmation() -> None:
    # act() prueft die Bestaetigung VOR jeglichem Netzwerkzugriff
    with pytest.raises(AdapterError) as exc_info:
        run(ProxmoxAdapter().act(make_config(), make_secrets(), "start", "101", confirmed=False))
    assert exc_info.value.state is AdapterState.NOT_CONFIGURED


def test_act_rejects_unsupported_action() -> None:
    config = make_config()
    with pytest.raises(AdapterConfigError):
        run(ProxmoxAdapter().act(config, make_secrets(), "stop", "101", confirmed=True))
    with pytest.raises(AdapterConfigError):
        run(ProxmoxAdapter().act(config, make_secrets(), "destroy", "101", confirmed=True))


def test_act_rejects_non_numeric_external_id() -> None:
    config = make_config()
    with pytest.raises(AdapterConfigError):
        run(ProxmoxAdapter().act(config, make_secrets(), "start", "abc", confirmed=True))
    with pytest.raises(AdapterConfigError):
        run(ProxmoxAdapter().act(config, make_secrets(), "start", "10.0.0.2", confirmed=True))
