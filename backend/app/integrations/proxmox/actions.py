"""Compute-Aktionen fuer Proxmox (Agent 3, R1).

Zwei Teile:

1. **Adapter-seitige Vorbereitung** (Node-/Endpoint-Aufloesung, sanfte
   Proxmox-Status-Endpoints). Keine erzwungenen Stops, keine Loeschungen,
   keine Migrationen — nur start/shutdown(ACPI bzw. ohne Force)/reboot.

2. **ActionJob-Orchestrierung** (`execute_compute_action`): duenner,
   allgemeiner Service ueber dem frozen ActionJob-Modell
   (``app.models.action_jobs``) — KEINE zweite Job-Tabelle, keine
   unabhaengige Job-Verwaltung. Jede Ausfuehrung ist:
     a. serverseitig RBAC-geprueft (frozen Key ``actions.run``, Operator+),
     b. auditiert (``app.audit.log.record_audit``),
     c. idempotenzbewusst (``idempotency_key`` auf ActionJob),
     d. statusgetrieben (pending → running → succeeded/failed).

Produktive Schreibaktionen bleiben hinter expliziter Freigabe (siehe
``docs/agent-reports/R1-proxmox.md``); in R1 laeuft dieser Pfad nur
gegen Mock-APIs in Tests.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterConfig, AdapterStatus, SecretsProvider
from app.adapters.errors import AdapterApiError, AdapterError
from app.audit.log import record_audit
from app.auth.rbac import has_permission
from app.errors import ErrorCode, http_error
from app.integrations.proxmox.client import ProxmoxClient
from app.models.action_jobs import ActionJob, ActionType, JobStatus
from app.models.integrations import Integration
from app.models.mixins import utcnow
from app.models.users import User

# frozen RBAC-Key (app.auth.rbac.PERMISSIONS) — Operator+
ACTIONS_RUN_PERMISSION = "actions.run"

# (API-Teil, Aktion) → Pfadtemplate. Sanft: keine 'force'-Parameter,
# kein /status/stop (erzwungener Stop) — bewusst NICHT enthalten.
_ACTION_ENDPOINTS: dict[tuple[str, str], str] = {
    ("qemu", "start"): "/nodes/{node}/qemu/{resource_id}/status/start",
    ("qemu", "shutdown"): "/nodes/{node}/qemu/{resource_id}/status/shutdown",  # ACPI
    ("qemu", "reboot"): "/nodes/{node}/qemu/{resource_id}/status/restart",  # ACPI
    ("lxc", "start"): "/nodes/{node}/lxc/{resource_id}/start",
    ("lxc", "shutdown"): "/nodes/{node}/lxc/{resource_id}/stop",  # ohne --force
    ("lxc", "reboot"): "/nodes/{node}/lxc/{resource_id}/restart",
}

_CLUSTER_RESOURCE_TYPE = {"qemu": "vm", "lxc": "container"}


async def resolve_target(client: ProxmoxClient, external_id: str) -> tuple[str, str]:
    """Loest ``(node, api)`` fuer eine VMID/CT-ID auf.

    Strategie: zuerst ``/cluster/resources`` (funktioniert auf Standalone
    wie im Cluster), sonst Node-fuer-Node-Abfrage. Liefert ``'qemu'``
    oder ``'lxc'`` als API-Teil.
    """
    for api in ("qemu", "lxc"):
        entries = await client.get_optional(
            "/cluster/resources", params={"type": _CLUSTER_RESOURCE_TYPE[api], "vmid": external_id}
        )
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get("node"):
                    return str(entry["node"]), api

    # Fallback ohne /cluster/resources (z. B. 403): Nodes durchfragen
    nodes = await client.get("/nodes")
    node_names = [str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("id")] if isinstance(nodes, list) else []
    for node in node_names:
        for api in ("qemu", "lxc"):
            data = await client.get_tolerant(f"/nodes/{node}/{api}/{external_id}")
            if data is not None:
                return node, api

    raise AdapterApiError(
        f"Ressource '{external_id}' (VM/LXC) wurde auf keinem Node gefunden",
        http_status=404,
    )


def action_endpoint(api: str, action: str, node: str, resource_id: str) -> str | None:
    """Endpoint-Pfad fuer eine Aktion; None = nicht (erlaubt) implementiert."""
    template = _ACTION_ENDPOINTS.get((api, action))
    if template is None:
        return None
    return template.format(node=node, resource_id=resource_id)


# --------------------------------------------------------------------- RBAC


def require_actions_run(user: User) -> None:
    """Serverseitige RBAC-Pruefung (frozen Key ``actions.run``, Operator+)."""
    if not has_permission(user.role, ACTIONS_RUN_PERMISSION):
        raise http_error(403, ErrorCode.FORBIDDEN, f"Berechtigung fehlend: {ACTIONS_RUN_PERMISSION}")


# ----------------------------------------------------------------- ActionJob


def submit_action_job(
    db: Session,
    *,
    integration: Integration,
    action: ActionType,
    external_resource_id: str,
    requested_by: uuid.UUID,
    idempotency_key: str | None = None,
    details: dict[str, Any] | None = None,
) -> tuple[ActionJob, bool]:
    """Legt einen ActionJob idempotent an (frozen Schema).

    ``idempotency_key`` ist AUFTRAGSEITIG zu verantworten (z. B.
    klientspezifischer Idempotency-Key). Ohne Key wird ein frischer
    UUID-Key verwendet (neuer Job). Existiert der Key bereits, wird der
    vorhandene Job zurueckgegeben (``created=False``) — es entsteht
    keine zweite, parallele Job-Instanz.
    """
    key = idempotency_key or f"auto-{uuid.uuid4()}"
    existing = db.scalar(select(ActionJob).where(ActionJob.idempotency_key == key))
    if existing is not None:
        return existing, False
    job = ActionJob(
        idempotency_key=key,
        action=action,
        integration_id=integration.id,
        external_resource_id=str(external_resource_id),
        requested_by=requested_by,
        status=JobStatus.PENDING,
        details=details or {},
    )
    db.add(job)
    db.flush()
    return job, True


# ------------------------------------------------------------------ executor


async def execute_compute_action(
    db: Session,
    *,
    adapter,
    config: AdapterConfig,
    secrets: SecretsProvider,
    integration: Integration,
    user: User,
    action: ActionType,
    external_id: str,
    confirmed: bool = True,
    idempotency_key: str | None = None,
    request: Request | None = None,
) -> ActionJob:
    """Fuehrt eine Compute-Aktion mit RBAC, Audit und Job-Handling aus.

    Liefert den ``ActionJob``; Adapter-Fehler werden NICHT weitergeworfen,
    sondern im Job (status=failed, error_state) getragen — der aufrufende
    Endpunkt (R2) entscheidet ueber die HTTP-Mapping. ``succeeded``
    bedeutet: die Proxmox-API hat die Aktion als asynchronen Task
    angenommen (UPID), NICHT dass sie bereits abgeschlossen ist.
    """
    require_actions_run(user)
    if not confirmed:
        raise http_error(422, ErrorCode.VALIDATION_ERROR, "Bestaetigung ist fuer die Aktion erforderlich")

    job, created = submit_action_job(
        db,
        integration=integration,
        action=action,
        external_resource_id=external_id,
        requested_by=user.id,
        idempotency_key=idempotency_key,
        details={"confirmed": True},
    )
    if not created:
        record_audit(
            db,
            user=user,
            action="actions.compute.replay",
            integration_id=integration.id,
            resource_id=external_id,
            request=request,
            details={"action": action.value, "idempotency_key": job.idempotency_key, "job_status": job.status.value},
        )
        return job

    record_audit(
        db,
        user=user,
        action=f"actions.compute.{action.value}",
        integration_id=integration.id,
        resource_id=external_id,
        request=request,
        details={"idempotency_key": job.idempotency_key, "external_id": external_id},
    )
    job.status = JobStatus.RUNNING
    job.started_at = utcnow()

    try:
        status: AdapterStatus = await adapter.act(config, secrets, action.value, external_id, confirmed=True)
    except AdapterError as exc:
        job.status = JobStatus.FAILED
        job.finished_at = utcnow()
        job.details = {**job.details, "error_state": exc.state.value, "error": exc.message[:512]}
        record_audit(
            db,
            user=user,
            action=f"actions.compute.{action.value}.failed",
            integration_id=integration.id,
            resource_id=external_id,
            request=request,
            details={"action": action.value, "state": exc.state.value, "error": exc.message[:512]},
        )
        return job

    job.status = JobStatus.SUCCEEDED
    job.finished_at = utcnow()
    job.details = {**job.details, "adapter_state": status.state.value, "task": status.message}
    record_audit(
        db,
        user=user,
        action=f"actions.compute.{action.value}.accepted",
        integration_id=integration.id,
        resource_id=external_id,
        request=request,
        details={"action": action.value, "task": status.message},
    )
    return job
