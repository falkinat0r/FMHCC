"""Inventar-Normalisierung/Deduplizierung (Foundation, frozen).

Einziger Schreibweg fuer Ressourcen aus Adapter-Discover. Dedupliziert nach
Resource-Key ``(integration, resource_type, external_id)``; waehlt
``last_seen_at``/``observed_at`` korrekt und legt Beziehungen mit Evidenz
an, wenn ein Parent existiert.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import ResourceRecord
from app.models.integrations import Integration
from app.models.mixins import utcnow
from app.models.resources import Resource, ResourceRelation, ResourceSource


@dataclass
class UpsertResult:
    created: int
    updated: int
    relations_created: int


def upsert_resources(
    db: Session,
    integration: Integration,
    records: list[ResourceRecord],
) -> UpsertResult:
    """Fuehrt Discover-Records idempotent in die Inventartabelle ein."""
    created = updated = relations_created = 0
    for record in records:
        existing = db.scalar(
            select(Resource).where(
                Resource.integration_id == integration.id,
                Resource.resource_type == record.resource_type,
                Resource.external_id == record.external_id,
            )
        )
        observed = record.observed_at
        if existing is None:
            resource = Resource(
                integration_id=integration.id,
                resource_type=record.resource_type,
                external_id=record.external_id,
                name=record.name,
                status=record.status,
                source=ResourceSource.API,
                payload=record.payload,
                observed_at=observed,
                last_seen_at=observed,
                first_seen_at=observed,
            )
            db.add(resource)
            created += 1
        else:
            existing.name = record.name
            existing.status = record.status
            existing.payload = record.payload
            existing.observed_at = observed
            existing.last_seen_at = observed
            updated += 1

        # Flush stellt sicher, dass die (ggf. neue) Ressource eine ID hat,
        # bevor die Relation geprüft wird.
        db.flush()
        resource = existing if existing is not None else db.scalar(
            select(Resource).where(
                Resource.integration_id == integration.id,
                Resource.resource_type == record.resource_type,
                Resource.external_id == record.external_id,
            )
        )

        if (
            resource is not None
            and record.parent_external_id
            and record.parent_resource_type is not None
        ):
            parent = db.scalar(
                select(Resource).where(
                    Resource.integration_id == integration.id,
                    Resource.resource_type == record.parent_resource_type,
                    Resource.external_id == record.parent_external_id,
                )
            )
            if parent is not None:
                relation_exists = db.scalar(
                    select(ResourceRelation.id).where(
                        ResourceRelation.source_resource_id == parent.id,
                        ResourceRelation.target_resource_id == resource.id,
                        ResourceRelation.relation_type == record.relation_type,
                    )
                )
                if relation_exists is None:
                    db.add(
                        ResourceRelation(
                            source_resource_id=parent.id,
                            target_resource_id=resource.id,
                            relation_type=record.relation_type,
                            evidence=ResourceSource.API,
                            observed_at=utcnow(),
                        )
                    )
                    relations_created += 1

    # Abschluss-Flush: Alle neuen/aktualisierten Ressourcen und Relationen
    # sind nach dem Rueckgabewert in der Transaktion persistiert (sichtbar
    # fuer nachfolgende Queries desselben Sessions, auch bei autoflush=False).
    db.flush()
    return UpsertResult(created=created, updated=updated, relations_created=relations_created)
