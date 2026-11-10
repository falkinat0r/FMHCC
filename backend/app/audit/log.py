"""Audit-Service (Foundation, frozen Schnittstelle).

Audit-Events werden nur hinzugefuegt, nie veraeendert. Details werden
maskiert (Secret-Felder). Bei User-Loeschung bleibt das Event erhalten
(FK ON DELETE SET NULL, Username ist redundant gespeichert).
"""

from __future__ import annotations

import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.logging_setup import mask_fields
from app.models.audit import AuditEvent
from app.models.mixins import utcnow
from app.models.users import User


def record_audit(
    db: Session,
    *,
    user: User | None,
    action: str,
    request: Request | None = None,
    integration_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
    commit: bool = False,
) -> AuditEvent:
    """Legt ein Audit-Event an (Commit erfolgt durch die Request-Session).

    ``commit=True`` fuer Fehler-Pfade, die danach eine Exception werfen:
    Die Request-Session rollt bei Fehlern zurueck und wuerde das Event
    sonst verworfen (z. B. fehlgeschlagener Login/Bootstrap).
    """
    ip = None
    user_agent = None
    if request is not None:
        ip = request.client.host if request.client else None
        user_agent = (request.headers.get("user-agent") or "")[:256] or None
    event = AuditEvent(
        user_id=user.id if user else None,
        username=user.username if user else None,
        action=action,
        integration_id=integration_id,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip,
        user_agent=user_agent,
        details=mask_fields(details or {}),
        created_at=utcnow(),
    )
    db.add(event)
    db.flush()
    if commit:
        db.commit()
    return event
