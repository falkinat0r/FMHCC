"""Integrations-Endpoints (frozen Routenplan, R0).

RBAC:
- Lesen: viewer+
- Konfigurieren/Verify/Delete: admin
Verify nutzt die Adapter-Registry; in R0 ist sie leer => ehrliches
``not_implemented`` (501), kein Stub.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterConfig, AdapterState
from app.adapters.errors import AdapterError
from app.adapters.secrets import EnvSecretsProvider
from app.audit.log import record_audit
from app.auth.rbac import require_permission
from app.contracts.integrations import (
    IntegrationCreate,
    IntegrationOut,
    VerifyResponse,
)
from app.contracts.pagination import Paged, paginate
from app.db.session import get_db
from app.errors import ErrorCode, http_error
from app.integrations import registry
from app.models.action_jobs import ActionJob
from app.models.integrations import Integration, IntegrationStatus
from app.models.users import User

router = APIRouter(prefix="/integrations")


def _to_out(integration: Integration, *, viewer: bool) -> IntegrationOut:
    return IntegrationOut(
        id=integration.id,
        integration_id=integration.integration_id,
        name=integration.name,
        adapter=integration.adapter,
        status=integration.status,
        capabilities=integration.capabilities or {},
        base_url=str(integration.base_url) if integration.base_url else None,
        secret_ref=None if viewer else integration.secret_ref,
        last_verified_at=integration.last_verified_at,
        last_error=integration.last_error,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


def _get_by_slug(db: Session, integration_id: str) -> Integration | None:
    return db.scalar(select(Integration).where(Integration.integration_id == integration_id))


@router.get("", response_model=Paged[IntegrationOut])
def list_integrations(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("integrations.read")),
    db: Session = Depends(get_db),
) -> Paged[IntegrationOut]:
    total = db.scalar(select(func.count()).select_from(Integration)) or 0
    items = db.scalars(
        select(Integration).order_by(Integration.integration_id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    is_viewer = user.role.value == "viewer"
    return paginate([_to_out(i, viewer=is_viewer) for i in items], total, page, page_size)


@router.get("/{integration_id}", response_model=IntegrationOut)
def get_integration(
    integration_id: str,
    request: Request,
    user: User = Depends(require_permission("integrations.read")),
    db: Session = Depends(get_db),
) -> IntegrationOut:
    integration = _get_by_slug(db, integration_id)
    if integration is None:
        raise http_error(404, ErrorCode.NOT_FOUND, "Integration nicht gefunden")
    return _to_out(integration, viewer=user.role.value == "viewer")


@router.put("/{integration_id}", response_model=IntegrationOut)
def upsert_integration(
    integration_id: str,
    payload: IntegrationCreate,
    request: Request,
    admin: User = Depends(require_permission("integrations.manage")),
    db: Session = Depends(get_db),
) -> IntegrationOut:
    """Erzeugt oder aktualisiert eine Integration (nur admin).

    Rein lokale Konfiguration — es findet hier KEIN Zugriff auf das Zielsystem
    statt. Verify ist ein separater, auditiertender Endpoint.
    """
    if payload.integration_id != integration_id:
        raise http_error(422, ErrorCode.VALIDATION_ERROR, "integration_id stimmt nicht mit der URL ueberein")

    integration = _get_by_slug(db, integration_id)
    if integration is None:
        integration = Integration(integration_id=integration_id)
        db.add(integration)
    integration.name = payload.name
    integration.adapter = payload.adapter
    integration.base_url = str(payload.base_url) if payload.base_url else None
    integration.secret_ref = payload.secret_ref
    integration.status = IntegrationStatus.CONFIGURED
    integration.last_error = None
    record_audit(
        db,
        user=admin,
        action="integrations.configure",
        request=request,
        integration_id=integration.id,
        details={"integration_id": integration_id, "adapter": payload.adapter.value},
    )
    db.flush()
    return _to_out(integration, viewer=False)


@router.post("/{integration_id}/verify", response_model=VerifyResponse)
async def verify_integration(
    integration_id: str,
    request: Request,
    admin: User = Depends(require_permission("integrations.manage")),
    db: Session = Depends(get_db),
) -> VerifyResponse:
    """Verbindung + Credentials pruefen (nur lesende Requests am Zielsystem)."""
    integration = _get_by_slug(db, integration_id)
    if integration is None:
        raise http_error(404, ErrorCode.NOT_FOUND, "Integration nicht gefunden")

    checked_at = datetime.now(UTC)
    integration.last_verified_at = checked_at
    adapter_cls = registry.get_adapter(integration.adapter)
    if adapter_cls is None:
        integration.status = IntegrationStatus.NOT_CONFIGURED
        integration.last_error = f"Kein Adapter fuer '{integration.adapter.value}' in diesem Build registriert"
        record_audit(
            db,
            user=admin,
            action="integrations.verify.skipped",
            request=request,
            integration_id=integration.id,
        )
        return VerifyResponse(
            integration_id=integration.integration_id,
            status="not_implemented",
            message=integration.last_error,
            capabilities={},
            checked_at=checked_at,
        )

    config = AdapterConfig(
        base_url=str(integration.base_url) if integration.base_url else None,
        secret_ref=integration.secret_ref,
    )
    adapter = adapter_cls()
    try:
        status = await adapter.verify(config, EnvSecretsProvider())
    except AdapterError as exc:
        integration.status = IntegrationStatus.ERROR
        integration.last_error = exc.message[:512]
        record_audit(
            db,
            user=admin,
            action="integrations.verify.failed",
            request=request,
            integration_id=integration.id,
            details={"state": exc.state.value},
        )
        return VerifyResponse(
            integration_id=integration.integration_id,
            status=exc.state.value,
            message=exc.message,
            checked_at=checked_at,
        )

    if status.state is AdapterState.OK:
        integration.status = IntegrationStatus.CONFIGURED
        integration.last_error = None
        capabilities = await adapter.capabilities(config, EnvSecretsProvider())
        integration.capabilities = {
            "features": capabilities.features,
            "api_version": capabilities.api_version,
            **capabilities.extra,
        }
    else:
        integration.status = IntegrationStatus.ERROR
        integration.last_error = (status.message or status.state.value)[:512]

    record_audit(
        db,
        user=admin,
        action="integrations.verify.success",
        request=request,
        integration_id=integration.id,
        details={"state": status.state.value},
    )
    return VerifyResponse(
        integration_id=integration.integration_id,
        status=status.state.value,
        message=status.message,
        capabilities=integration.capabilities or {},
        api_version=status.api_version,
        checked_at=checked_at,
    )


@router.delete("/{integration_id}", status_code=204)
def delete_integration(
    integration_id: str,
    request: Request,
    admin: User = Depends(require_permission("integrations.manage")),
    db: Session = Depends(get_db),
) -> Response:
    integration = _get_by_slug(db, integration_id)
    if integration is None:
        raise http_error(404, ErrorCode.NOT_FOUND, "Integration nicht gefunden")
    # Action-Jobs referenzieren die Integration (FK RESTRICT, bewusst:
    # Aktionshistorie bleibt referenzintakt). Loeschen wuerde sonst einen
    # rohen IntegrityError/500 ausloesen — saubere 409-Antwort statt.
    job_count = db.scalar(select(func.count()).select_from(ActionJob).where(ActionJob.integration_id == integration.id))
    if job_count:
        raise http_error(
            409,
            ErrorCode.CONFLICT,
            f"Integration hat {job_count} Action-Jobs; Loeschen ist erst moeglich, wenn die Historie entfernt wird",
        )
    db.delete(integration)
    record_audit(
        db,
        user=admin,
        action="integrations.delete",
        request=request,
        integration_id=integration.id,
        details={"integration_id": integration_id},
    )
    db.flush()
    return Response(status_code=204)
