"""Ressourcen-/Inventar-Contract (frozen, R0).

Identitaet: (integration_id, resource_type, external_id).
Zustände: healthy/degraded/down/unknown/not_configured — fachlich getrennt,
niemals Zufallswerte. Alle Zeitstempel UTC.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.resources import ResourceSource, ResourceStatus, ResourceType


class ResourceOut(BaseModel):
    id: uuid.UUID
    integration_id: str
    resource_type: ResourceType
    external_id: str
    name: str | None = None
    status: ResourceStatus
    source: ResourceSource
    payload: dict[str, Any]
    observed_at: datetime | None = None
    last_seen_at: datetime | None = None
    first_seen_at: datetime | None = None


class ResourceRelationOut(BaseModel):
    id: uuid.UUID
    source_resource_id: uuid.UUID
    target_resource_id: uuid.UUID
    source_name: str | None = None
    target_name: str | None = None
    relation_type: str
    evidence: ResourceSource
    note: str | None = None
    observed_at: datetime | None = None


class ResourceDetailOut(ResourceOut):
    relations: list[ResourceRelationOut] = []
