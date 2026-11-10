"""Ressourcen-/Inventar-Endpoints (viewer+, frozen Routenplan R0).

R0: nur lesen. Schreibwege laufen ausschliesslich ueber
``app.inventory.base.upsert_resources`` aus Adapter-Discover.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.rbac import require_permission
from app.contracts.pagination import Paged, paginate
from app.contracts.resources import ResourceDetailOut, ResourceOut, ResourceRelationOut
from app.db.session import get_db
from app.errors import ErrorCode, http_error
from app.models.integrations import Integration
from app.models.resources import Resource, ResourceRelation
from app.models.users import User

router = APIRouter(prefix="/resources")


def _to_out(resource: Resource, integration_slug: str) -> ResourceOut:
    return ResourceOut(
        id=resource.id,
        integration_id=integration_slug,
        resource_type=resource.resource_type,
        external_id=resource.external_id,
        name=resource.name,
        status=resource.status,
        source=resource.source,
        payload=resource.payload or {},
        observed_at=resource.observed_at,
        last_seen_at=resource.last_seen_at,
        first_seen_at=resource.first_seen_at,
    )


@router.get("", response_model=Paged[ResourceOut])
def list_resources(
    request: Request,
    integration: str | None = Query(None, description="Integration-Slug filtern"),
    resource_type: str | None = Query(None, description="z. B. host | vm | lxc"),
    status: str | None = Query(None, description="healthy | degraded | down | unknown | not_configured"),
    q: str | None = Query(None, max_length=128, description="Volltext auf name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("resources.read")),
    db: Session = Depends(get_db),
) -> Paged[ResourceOut]:
    query = select(Resource)
    count_query = select(func.count()).select_from(Resource)

    if integration is not None:
        integration_row = db.scalar(select(Integration).where(Integration.integration_id == integration))
        if integration_row is None:
            return paginate([], 0, page, page_size)
        query = query.where(Resource.integration_id == integration_row.id)
        count_query = count_query.where(Resource.integration_id == integration_row.id)
    if resource_type is not None:
        query = query.where(Resource.resource_type == resource_type)
        count_query = count_query.where(Resource.resource_type == resource_type)
    if status is not None:
        query = query.where(Resource.status == status)
        count_query = count_query.where(Resource.status == status)
    if q is not None:
        like = f"%{q}%"
        query = query.where(Resource.name.like(like))
        count_query = count_query.where(Resource.name.like(like))

    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(Resource.last_seen_at.desc().nullslast(), Resource.id).offset((page - 1) * page_size).limit(page_size)
    ).all()

    slugs = {
        row.id: row.integration_id
        for row in db.scalars(select(Integration).where(Integration.id.in_([r.integration_id for r in rows]))).all()
    } if rows else {}
    items = [_to_out(r, slugs.get(r.integration_id, "unknown")) for r in rows]
    return paginate(items, total, page, page_size)


@router.get("/{resource_id}", response_model=ResourceDetailOut)
def get_resource(
    resource_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("resources.read")),
    db: Session = Depends(get_db),
) -> ResourceDetailOut:
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise http_error(404, ErrorCode.NOT_FOUND, "Ressource nicht gefunden")
    integration = db.get(Integration, resource.integration_id)
    slug = integration.integration_id if integration else "unknown"

    relations = db.scalars(
        select(ResourceRelation).where(
            (ResourceRelation.source_resource_id == resource.id) | (ResourceRelation.target_resource_id == resource.id)
        )
    ).all()
    related_ids = {rel.source_resource_id for rel in relations} | {rel.target_resource_id for rel in relations}
    names = {
        row.id: row.name
        for row in db.scalars(select(Resource).where(Resource.id.in_(list(related_ids)))).all()
    }
    relation_outs = [
        ResourceRelationOut(
            id=rel.id,
            source_resource_id=rel.source_resource_id,
            target_resource_id=rel.target_resource_id,
            source_name=names.get(rel.source_resource_id),
            target_name=names.get(rel.target_resource_id),
            relation_type=rel.relation_type,
            evidence=rel.evidence,
            note=rel.note,
            observed_at=rel.observed_at,
        )
        for rel in relations
    ]

    base = _to_out(resource, slug)
    return ResourceDetailOut(**base.model_dump(), relations=relation_outs)
