"""Audit-Endpoints (admin, frozen Routenplan R0)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.rbac import require_permission
from app.contracts.audit import AuditEventOut
from app.contracts.pagination import Paged, paginate
from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.users import User

router = APIRouter(prefix="/audit")


@router.get("", response_model=Paged[AuditEventOut])
def list_audit_events(
    request: Request,
    action: str | None = Query(None, max_length=64, description="Präfixfilter, z. B. 'auth.login'"),
    username: str | None = Query(None, max_length=64),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    admin: User = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db),
) -> Paged[AuditEventOut]:
    query = select(AuditEvent)
    count_query = select(func.count()).select_from(AuditEvent)
    if action is not None:
        query = query.where(AuditEvent.action.like(f"{action}%"))
        count_query = count_query.where(AuditEvent.action.like(f"{action}%"))
    if username is not None:
        query = query.where(AuditEvent.username == username)
        count_query = count_query.where(AuditEvent.username == username)

    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        AuditEventOut(
            id=row.id,
            username=row.username,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            details=row.details or {},
            created_at=row.created_at,
        )
        for row in rows
    ]
    return paginate(items, total, page, page_size)
