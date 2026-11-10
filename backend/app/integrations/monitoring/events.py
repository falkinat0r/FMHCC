"""Event-Normalisierung und Deduplizierung (Agent 4, R1).

Korvertiert system-spezifische Ereignisse (TrueNAS/ZFS, Uptime Kuma,
Alertmanager, …) in das vereinigte ``NormalizedEvent``-Modell aus base.py.

R0 hat bewusst keinen persistenten Event-Store (MASTER_PROMPT trennt
Hochauflösungs-Metrikdaten von der PostgreSQL-Inventardatenbank). Dieses
Modell ist der gemeinsame Contract; die persistente Ablage wird per
``docs/proposals/agent4-monitoring-api.md`` vorgeschlagen. Es entsteht
keinerlei konkurrierender zweiter Event-Datenbestand.

Deduplizierung:
- stabiler ``fingerprint`` (SHA-256): bei Quellen mit interner Event-ID
  ``source:event_id``; sonst ``source:typ:message:Minute-Bucket`` (absorbiert
  Uhrzeit-Drift und wiederholte Sammlungen desselben Vorfalls).
- ``EventDeduplicator``: in-memory LRU für einen Sammelzyklus.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.integrations.monitoring.base import (
    AlertStatus,
    EventSeverity,
    NormalizedEvent,
    ResourceRef,
)

__all__ = [
    "EventDeduplicator",
    "event_fingerprint",
    "normalize_event",
    "severity_from_raw",
    "status_from_raw",
]

_SEVERITY_ALIASES: dict[str, EventSeverity] = {
    "info": EventSeverity.INFO,
    "information": EventSeverity.INFO,
    "informational": EventSeverity.INFO,
    "notice": EventSeverity.INFO,
    "debug": EventSeverity.INFO,
    "warn": EventSeverity.WARNING,
    "warning": EventSeverity.WARNING,
    "medium": EventSeverity.WARNING,
    "high": EventSeverity.WARNING,
    "critical": EventSeverity.CRITICAL,
    "crit": EventSeverity.CRITICAL,
    "emergency": EventSeverity.CRITICAL,
    "fatal": EventSeverity.CRITICAL,
    "error": EventSeverity.CRITICAL,
    "severe": EventSeverity.CRITICAL,
}

_STATUS_ALIASES: dict[str, AlertStatus] = {
    "active": AlertStatus.ACTIVE,
    "firing": AlertStatus.ACTIVE,
    "pending": AlertStatus.ACTIVE,
    "resolved": AlertStatus.RESOLVED,
    "recovered": AlertStatus.RESOLVED,
    "ok": AlertStatus.RESOLVED,
    "closed": AlertStatus.RESOLVED,
}


def severity_from_raw(raw: Any, default: EventSeverity = EventSeverity.WARNING) -> EventSeverity:
    """Mappt einen Quell-Schweregrad (String) auf EventSeverity."""
    if not isinstance(raw, (str, int)):
        return default
    return _SEVERITY_ALIASES.get(str(raw).strip().lower(), default)


def status_from_raw(raw: Any, default: AlertStatus = AlertStatus.UNKNOWN) -> AlertStatus:
    """Mappt einen Quell-Status (String) auf AlertStatus."""
    if not isinstance(raw, str):
        return default
    return _STATUS_ALIASES.get(raw.strip().lower(), default)


def event_fingerprint(
    source: str,
    source_event_id: str | None,
    event_type: str,
    message: str,
    occurred_at: datetime,
) -> str:
    """Stabiler Dedup-Fingerprint (SHA-256-Hex).

    Mit interner Event-ID: deterministisch pro Quelle+Event.
    Ohne: Typ + Meldung + Minute-Bucket (identische Wiederholungen des
    gleichen Vorfalls kollidieren; Uhrzeit-Drift bleibt absorbiert).
    """
    if source_event_id:
        basis = f"{source}:{source_event_id}"
    else:
        bucket = occurred_at.astimezone(UTC).replace(second=0, microsecond=0)
        basis = f"{source}:{event_type}:{message}:{bucket.isoformat()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def normalize_event(
    *,
    source: str,
    raw: Mapping[str, Any],
    occurred_at: datetime,
    event_type: str | None = None,
    severity: EventSeverity | str | None = None,
    status: AlertStatus | str | None = None,
    resource: ResourceRef | None = None,
    default_severity: EventSeverity = EventSeverity.WARNING,
    resource_ref_keys: tuple[tuple[str, str], ...] = (),
) -> NormalizedEvent:
    """Erzeugt ein NormalizedEvent aus einem rohen Quell-Event (Mapping).

    Erwartete Roh-Schlüssel (alle optional): ``id``/``event_id``, ``type``/
    ``kind``, ``severity``/``level``, ``message``/``msg``, ``status``,
    ``resource_type``/``resource_external_id`` (nur mit resource_ref_keys
    deaktiviert; sonst explizite resource übergeben).
    """
    source_event_id: str | None = None
    for key in ("id", "event_id"):
        value = raw.get(key)
        if value is not None:
            source_event_id = str(value)
            break

    resolved_type = event_type or str(raw.get("type") or raw.get("kind") or "unknown")

    raw_severity = raw.get("severity", raw.get("level"))
    if severity is not None:
        resolved_severity = (
            severity
            if isinstance(severity, EventSeverity)
            else _SEVERITY_ALIASES.get(str(severity).strip().lower(), default_severity)
        )
    elif raw_severity is not None:
        resolved_severity = severity_from_raw(raw_severity, default_severity)
    else:
        resolved_severity = default_severity

    raw_status = raw.get("status")
    if status is not None:
        resolved_status = status if isinstance(status, AlertStatus) else status_from_raw(str(status))
    else:
        resolved_status = status_from_raw(raw_status)

    message = str(raw.get("message") or raw.get("msg") or resolved_type)

    if resource is None and resource_ref_keys:
        rt, ext = resource_ref_keys[0]
        resource_type_raw = raw.get(rt)
        external_raw = raw.get(ext)
        if resource_type_raw is not None and external_raw is not None:
            resource = ResourceRef(
                resource_type=str(resource_type_raw),
                external_id=str(external_raw),
            )

    received_at = datetime.now(UTC)
    fingerprint = event_fingerprint(
        source=source,
        source_event_id=source_event_id,
        event_type=resolved_type,
        message=message,
        occurred_at=occurred_at,
    )
    return NormalizedEvent(
        fingerprint=fingerprint,
        source=source,
        source_event_id=source_event_id,
        severity=resolved_severity,
        event_type=resolved_type,
        message=message,
        status=resolved_status,
        resource=resource,
        occurred_at=occurred_at,
        received_at=received_at,
    )


class EventDeduplicator:
    """In-memory Dedup (LRU) für einen Sammelzyklus.

    Kein Dauerzustand: pro Sammel-Zyklus neu anlegen (oder mit neuem
    Zeitfenster); der persistente Store folgt dem Contract-Vorschlag.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries muss positiv sein")
        self._max_entries = max_entries
        self._seen: OrderedDict[str, None] = OrderedDict()

    def is_new(self, event: NormalizedEvent) -> bool:
        """True, wenn der Event noch nicht gesehen wurde (und jetzt registriert)."""
        fingerprint = event.fingerprint
        if fingerprint in self._seen:
            self._seen.move_to_end(fingerprint)
            return False
        self._seen[fingerprint] = None
        while len(self._seen) > self._max_entries:
            self._seen.popitem(last=False)
        return True

    def __len__(self) -> int:
        return len(self._seen)
