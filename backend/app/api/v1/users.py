"""User-Management-Endpoints (admin, frozen Routenplan R0)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.audit.log import record_audit
from app.auth.rbac import require_permission
from app.contracts.pagination import Paged, paginate
from app.contracts.users import UserCreate, UserOut, UserUpdate
from app.db.session import get_db
from app.errors import ErrorCode, http_error
from app.models.users import User
from app.users import service as user_service

router = APIRouter(prefix="/users")


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


@router.get("", response_model=Paged[UserOut])
def list_users(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    admin: User = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
) -> Paged[UserOut]:
    items, total = user_service.list_users(db, page=page, page_size=page_size)
    return paginate([_to_out(u) for u in items], total, page, page_size)


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    admin: User = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
) -> UserOut:
    user = user_service.create_user(
        db,
        username=payload.username,
        password=payload.password,
        role=payload.role,
        display_name=payload.display_name,
    )
    record_audit(db, user=admin, action="users.create", request=request, resource_type="user", resource_id=user.username)
    return _to_out(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    admin: User = Depends(require_permission("users.manage")),
    db: Session = Depends(get_db),
) -> UserOut:
    user = user_service.get_user(db, user_id)
    if user is None:
        raise http_error(404, ErrorCode.NOT_FOUND, "User nicht gefunden")
    updated = user_service.update_user(
        db,
        user,
        role=payload.role,
        is_active=payload.is_active,
        display_name=payload.display_name,
    )
    record_audit(
        db,
        user=admin,
        action="users.update",
        request=request,
        resource_type="user",
        resource_id=updated.username,
        details={"changes": [k for k in ("role", "is_active", "display_name") if getattr(payload, k) is not None]},
    )
    return _to_out(updated)
