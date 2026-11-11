"""ActionJob-Domainservice (R1).

Verantwortung: serverseitige Pruefung von Rolle/Berechtigung, Erzeugung
eindeutiger Jobs (UUID), idempotenzbewusste Wiederholung, definierte
Statusuebergänge (State-Machine) und Audit. Es wird HIER KEINE
Infrastrukturaktion ausgefuehrt — die konkrete Adapter-Ausfuehrung und die
zugehoerigen API-Endpunkte sind Aufgabe von Agent 3 (Proxmox) bzw.
spaeteren Releases.

Status-State-Machine (frozen Semantik):
    pending    -> running | cancelled
    running    -> succeeded | failed | cancelled
    succeeded  -> (terminal)
    failed     -> (terminal)
    cancelled  -> (terminal)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.actions import states
from app.audit.log import record_audit
from app.auth.rbac import has_permission
from app.errors import ErrorCode, http_error
from app.models.action_jobs import ActionJob, ActionType, JobStatus
from app.models.integrations import Integration
from app.models.mixins import utcnow
from app.models.users import User


def _require_action_actor(db: Session, actor: User | None) -> User:
    """Serverseitige RBAC-Pruefung fuer jede Aktions-Aktion.

    - Muss authentifiziert + aktiv sein.
    - Muss die Berechtigung ``actions.run`` haben (operator+).
    """
    if actor is None or not actor.is_active:
        raise http_error(401, ErrorCode.UNAUTHENTICATED, "Anmeldung erforderlich")
    if not has_permission(actor.role, "actions.run"):
        raise http_error(403, ErrorCode.FORBIDDEN, "Berechtigung fehlend: actions.run")
    return actor


def get_job(db: Session, job_id: uuid.UUID) -> ActionJob | None:
    return db.get(ActionJob, job_id)


def find_by_idempotency_key(db: Session, idempotency_key: str) -> ActionJob | None:
    return db.scalar(select(ActionJob).where(ActionJob.idempotency_key == idempotency_key))


def create_job(
    db: Session,
    *,
    actor: User,
    integration: Integration,
    action: ActionType,
    external_resource_id: str,
    idempotency_key: str,
    details: dict | None = None,
    request: Request | None = None,
) -> ActionJob:
    """Erzeugt einen Action-Job (pending) mit eindeutiger UUID.

    Idempotenz: Wenn fuer dieselben Parameter (actor, action,
    external_resource_id) bereits ein Job mit demselben ``idempotency_key``
    existiert, wird er zurueckgegeben, statt einen Duplikat zu erzeugen.
    """
    _require_action_actor(db, actor)

    if not external_resource_id:
        raise http_error(422, ErrorCode.VALIDATION_ERROR, "external_resource_id fehlt")
    if not idempotency_key:
        raise http_error(422, ErrorCode.VALIDATION_ERROR, "idempotency_key fehlt")

    existing = find_by_idempotency_key(db, idempotency_key)
    if existing is not None:
        # Gleicher Key + identische Zielressource => idempotente Wiederholung.
        if (
            existing.action == action
            and existing.integration_id == integration.id
            and existing.external_resource_id == external_resource_id
            and existing.requested_by == actor.id
        ):
            return existing
        raise http_error(
            409,
            ErrorCode.CONFLICT,
            "idempotency_key ist bereits fuer eine andere Aktion vergeben",
        )

    job = ActionJob(
        idempotency_key=idempotency_key,
        action=action,
        integration_id=integration.id,
        external_resource_id=external_resource_id,
        requested_by=actor.id,
        status=JobStatus.PENDING,
        details=details or {},
    )
    db.add(job)
    db.flush()

    record_audit(
        db,
        user=actor,
        action="actions.create",
        request=request,
        integration_id=integration.id,
        resource_type=action.value,
        resource_id=external_resource_id,
        details={"job_id": str(job.id), "idempotency_key": idempotency_key},
    )
    db.flush()
    return job


def transition(
    db: Session,
    *,
    job: ActionJob,
    to_status: JobStatus,
    actor: User,
    request: Request | None = None,
    reason: str | None = None,
) -> ActionJob:
    """Fuehrt einen definierten Statusuebergang durch (State-Machine).

    Unerlaubte Uebergänge => 409. Zeitstempel (started_at/finished_at)
    werden automatisch gesetzt. Jeder Uebergang wird auditiert.
    """
    _require_action_actor(db, actor)

    from_status = job.status
    allowed = states.ALLOWED_TRANSITIONS[from_status]
    if to_status not in allowed:
        raise http_error(
            409,
            ErrorCode.CONFLICT,
            f"Statusuebergang {from_status.value} -> {to_status.value} ist nicht erlaubt",
        )

    job.status = to_status
    if to_status is JobStatus.RUNNING and job.started_at is None:
        job.started_at = utcnow()
    if to_status in states.TERMINAL_STATUSES:
        job.finished_at = utcnow()

    details = {"job_id": str(job.id), "from": from_status.value}
    if reason is not None:
        details["reason"] = reason
    record_audit(
        db,
        user=actor,
        action=f"actions.transition.{to_status.value}",
        request=request,
        integration_id=job.integration_id,
        resource_type=job.action.value,
        resource_id=job.external_resource_id,
        details=details,
    )
    db.flush()
    return job


def list_jobs(
    db: Session,
    *,
    integration_id: uuid.UUID | None = None,
    status: JobStatus | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[ActionJob], int]:
    query = select(ActionJob)
    count_query = select(func.count()).select_from(ActionJob)
    if integration_id is not None:
        query = query.where(ActionJob.integration_id == integration_id)
        count_query = count_query.where(ActionJob.integration_id == integration_id)
    if status is not None:
        query = query.where(ActionJob.status == status)
        count_query = count_query.where(ActionJob.status == status)

    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(ActionJob.created_at.desc(), ActionJob.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(rows), total


def active_job_for_resource(
    db: Session,
    *,
    integration: Integration,
    external_resource_id: str,
    action: ActionType,
) -> ActionJob | None:
    """Liefert einen offenen (pending/running) Job fuer dieselbe Ressource+Aktion.

    Idempotenzbewusstes Job-Handling: verhindert doppelte parallele
    Start-/Shutdown-Anfuerungen auf dieselbe Ressource.
    """
    return db.scalar(
        select(ActionJob).where(
            ActionJob.integration_id == integration.id,
            ActionJob.external_resource_id == external_resource_id,
            ActionJob.action == action,
            ActionJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
    )


def is_terminal(status: JobStatus) -> bool:
    return status in states.TERMINAL_STATUSES


def can_transition(status: JobStatus, to_status: JobStatus) -> bool:
    return to_status in states.ALLOWED_TRANSITIONS[status]


def status_timestamps(job: ActionJob) -> dict[str, datetime | None]:
    return {"started_at": job.started_at, "finished_at": job.finished_at}
