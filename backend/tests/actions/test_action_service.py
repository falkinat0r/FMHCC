"""ActionJob-Service-Tests: RBAC, Idempotenz, State-Machine, Audit (R1).

Keine echte Infrastruktur wird angeruehrt — nur die serverseitige
Dienstlogik gegen die (frozen) action_jobs-Tabelle.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.actions import service as actions
from app.actions import states
from app.auth.hashing import hash_password
from app.errors import ApiError
from app.models.action_jobs import ActionJob, ActionType, JobStatus
from app.models.audit import AuditEvent
from app.models.integrations import Integration, IntegrationStatus
from app.models.users import Role, User


def _integration(db) -> Integration:
    integration = Integration(
        integration_id="pve-action",
        name="Proxmox Action",
        adapter="proxmox",
        status=IntegrationStatus.CONFIGURED,
        capabilities={},
    )
    db.add(integration)
    db.flush()
    return integration


def _user(db, *, username: str, role: Role, is_active: bool = True) -> User:
    user = User(
        username=username,
        role=role,
        password_hash=hash_password("passwort-12345"),
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def test_create_job_requires_authenticated_active_actor(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op", role=Role.OPERATOR, is_active=False)
    with pytest.raises(ApiError) as exc:
        actions.create_job(
            db,
            actor=operator,
            integration=integration,
            action=ActionType.START,
            external_resource_id="101",
            idempotency_key="k-1",
        )
    assert exc.value.status_code == 401


def test_create_job_rejects_viewer_role(db) -> None:
    integration = _integration(db)
    viewer = _user(db, username="viewer", role=Role.VIEWER)
    with pytest.raises(ApiError) as exc:
        actions.create_job(
            db,
            actor=viewer,
            integration=integration,
            action=ActionType.START,
            external_resource_id="101",
            idempotency_key="k-2",
        )
    assert exc.value.status_code == 403
    assert "actions.run" in exc.value.message


def test_create_job_operator_allowed_and_unique_id(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op2", role=Role.OPERATOR)
    job = actions.create_job(
        db,
        actor=operator,
        integration=integration,
        action=ActionType.SHUTDOWN,
        external_resource_id="102",
        idempotency_key="k-3",
        details={"reason": "wartung"},
    )
    assert isinstance(job.id, uuid.UUID)
    assert job.status is JobStatus.PENDING
    assert job.requested_by == operator.id
    assert job.integration_id == integration.id
    assert job.external_resource_id == "102"
    assert job.details == {"reason": "wartung"}


def test_create_job_requires_resource_and_key(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op3", role=Role.OPERATOR)
    with pytest.raises(ApiError) as no_resource:
        actions.create_job(
            db, actor=operator, integration=integration, action=ActionType.START,
            external_resource_id="", idempotency_key="k-4",
        )
    assert no_resource.value.status_code == 422
    with pytest.raises(ApiError) as no_key:
        actions.create_job(
            db, actor=operator, integration=integration, action=ActionType.START,
            external_resource_id="101", idempotency_key="",
        )
    assert no_key.value.status_code == 422


def test_idempotent_repeat_returns_existing_job(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op4", role=Role.OPERATOR)
    first = actions.create_job(
        db, actor=operator, integration=integration, action=ActionType.START,
        external_resource_id="101", idempotency_key="idem-x",
    )
    second = actions.create_job(
        db, actor=operator, integration=integration, action=ActionType.START,
        external_resource_id="101", idempotency_key="idem-x",
    )
    assert second.id == first.id
    assert len(db.scalars(select(ActionJob).where(ActionJob.idempotency_key == "idem-x")).all()) == 1


def test_idempotency_key_collision_conflicts(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op5", role=Role.OPERATOR)
    actions.create_job(
        db, actor=operator, integration=integration, action=ActionType.START,
        external_resource_id="101", idempotency_key="idem-y",
    )
    with pytest.raises(ApiError) as exc:
        actions.create_job(
            db, actor=operator, integration=integration, action=ActionType.REBOOT,
            external_resource_id="101", idempotency_key="idem-y",
        )
    assert exc.value.status_code == 409


def test_transition_valid_pending_to_running_sets_started_at(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op6", role=Role.OPERATOR)
    job = actions.create_job(
        db, actor=operator, integration=integration, action=ActionType.START,
        external_resource_id="101", idempotency_key="t-1",
    )
    updated = actions.transition(db, job=job, to_status=JobStatus.RUNNING, actor=operator)
    assert updated.status is JobStatus.RUNNING
    assert updated.started_at is not None
    assert updated.finished_at is None


def test_transition_running_to_terminal_sets_finished_at(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op7", role=Role.OPERATOR)
    job = actions.create_job(
        db, actor=operator, integration=integration, action=ActionType.START,
        external_resource_id="101", idempotency_key="t-2",
    )
    actions.transition(db, job=job, to_status=JobStatus.RUNNING, actor=operator)
    done = actions.transition(db, job=job, to_status=JobStatus.SUCCEEDED, actor=operator)
    assert done.status is JobStatus.SUCCEEDED
    assert done.finished_at is not None


def test_transition_invalid_is_rejected(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op8", role=Role.OPERATOR)
    job = actions.create_job(
        db, actor=operator, integration=integration, action=ActionType.START,
        external_resource_id="101", idempotency_key="t-3",
    )
    # pending -> succeeded ist undefiniert
    with pytest.raises(ApiError) as exc:
        actions.transition(db, job=job, to_status=JobStatus.SUCCEEDED, actor=operator)
    assert exc.value.status_code == 409
    assert job.status is JobStatus.PENDING


def test_terminal_states_are_final(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op9", role=Role.OPERATOR)
    job = actions.create_job(
        db, actor=operator, integration=integration, action=ActionType.START,
        external_resource_id="101", idempotency_key="t-4",
    )
    actions.transition(db, job=job, to_status=JobStatus.RUNNING, actor=operator)
    actions.transition(db, job=job, to_status=JobStatus.FAILED, actor=operator)
    with pytest.raises(ApiError) as exc:
        actions.transition(db, job=job, to_status=JobStatus.RUNNING, actor=operator)
    assert exc.value.status_code == 409
    assert actions.is_terminal(job.status) is True


def test_transition_requires_operator(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op10", role=Role.OPERATOR)
    viewer = _user(db, username="viewer10", role=Role.VIEWER)
    job = actions.create_job(
        db, actor=operator, integration=integration, action=ActionType.START,
        external_resource_id="101", idempotency_key="t-5",
    )
    with pytest.raises(ApiError) as exc:
        actions.transition(db, job=job, to_status=JobStatus.RUNNING, actor=viewer)
    assert exc.value.status_code == 403


def test_state_machine_matrix_is_fully_defined() -> None:
    # Jeder Status muss einen Eintrag haben (vollstaendige Matrix).
    assert set(states.ALLOWED_TRANSITIONS.keys()) == set(JobStatus)
    # Alle erlaubten Ziele sind gueltige Status.
    for allowed in states.ALLOWED_TRANSITIONS.values():
        for target in allowed:
            assert target in JobStatus
    # Terminal-Zustaende haben keine Ausgaenge.
    for terminal in states.TERMINAL_STATUSES:
        assert states.ALLOWED_TRANSITIONS[terminal] == frozenset()
    # Grunduebergänge existieren.
    assert JobStatus.RUNNING in states.ALLOWED_TRANSITIONS[JobStatus.PENDING]
    assert JobStatus.SUCCEEDED in states.ALLOWED_TRANSITIONS[JobStatus.RUNNING]


def test_actions_are_audited(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op11", role=Role.OPERATOR)
    job = actions.create_job(
        db, actor=operator, integration=integration, action=ActionType.START,
        external_resource_id="101", idempotency_key="a-1",
    )
    actions.transition(db, job=job, to_status=JobStatus.RUNNING, actor=operator)
    db.commit()

    events = db.scalars(select(AuditEvent).where(AuditEvent.action.like("actions.%"))).all()
    action_names = {event.action for event in events}
    assert "actions.create" in action_names
    assert "actions.transition.running" in action_names
    # Audit referenziert den Job und den Actor.
    create_event = next(event for event in events if event.action == "actions.create")
    assert create_event.username == "op11"
    assert create_event.details["job_id"] == str(job.id)
    assert str(create_event.resource_id) == "101"


def test_active_job_for_resource_finds_open_job(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op12", role=Role.OPERATOR)
    job = actions.create_job(
        db, actor=operator, integration=integration, action=ActionType.START,
        external_resource_id="101", idempotency_key="open-1",
    )
    assert actions.active_job_for_resource(
        db, integration=integration, external_resource_id="101", action=ActionType.START
    ).id == job.id
    actions.transition(db, job=job, to_status=JobStatus.RUNNING, actor=operator)
    actions.transition(db, job=job, to_status=JobStatus.SUCCEEDED, actor=operator)
    assert (
        actions.active_job_for_resource(
            db, integration=integration, external_resource_id="101", action=ActionType.START
        )
        is None
    )


def test_duplicate_idempotency_key_is_db_enforced(db) -> None:
    integration = _integration(db)
    operator = _user(db, username="op13", role=Role.OPERATOR)
    db.add(
        ActionJob(
            idempotency_key="raw-1",
            action=ActionType.START,
            integration_id=integration.id,
            external_resource_id="101",
            requested_by=operator.id,
            status=JobStatus.PENDING,
            details={},
        )
    )
    db.flush()
    with pytest.raises(IntegrityError):
        db.add(
            ActionJob(
                idempotency_key="raw-1",
                action=ActionType.START,
                integration_id=integration.id,
                external_resource_id="101",
                requested_by=operator.id,
                status=JobStatus.PENDING,
                details={},
            )
        )
        db.flush()
