"""Event-Normalisierung/-Dedup-Tests (Agent 4, R1).

Deckt ab: Severity-/Status-Mapping, Fingerprint-Stabilitaet (mit/ohne
internen Event-ID), Minuten-Bucket, Dedup (neu vs. duplicate), LRU-Eviction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.monitoring.base import AlertStatus, EventSeverity, ResourceRef
from app.integrations.monitoring.events import (
    EventDeduplicator,
    event_fingerprint,
    normalize_event,
    severity_from_raw,
    status_from_raw,
)


def test_severity_mapping() -> None:
    assert severity_from_raw("critical") is EventSeverity.CRITICAL
    assert severity_from_raw("warn") is EventSeverity.WARNING
    assert severity_from_raw("INFO") is EventSeverity.INFO
    assert severity_from_raw("severe") is EventSeverity.CRITICAL
    assert severity_from_raw("nichts-kanonisches") is EventSeverity.WARNING  # Default
    assert severity_from_raw(None) is EventSeverity.WARNING


def test_status_mapping() -> None:
    assert status_from_raw("firing") is AlertStatus.ACTIVE
    assert status_from_raw("resolved") is AlertStatus.RESOLVED
    assert status_from_raw("recovered") is AlertStatus.RESOLVED
    assert status_from_raw("was-weiss-ich") is AlertStatus.UNKNOWN


def test_fingerprint_with_event_id_is_stable() -> None:
    ts = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    fp1 = event_fingerprint("truenas", "evt-42", "zfs", "Pool degraded", ts)
    fp2 = event_fingerprint("truenas", "evt-42", "zfs", "Pool degraded", ts + timedelta(seconds=5))
    assert fp1 == fp2  # Zeit-Drift irrelevant, wenn Event-ID vorhanden
    assert len(fp1) == 64  # SHA-256-Hex


def test_fingerprint_without_event_id_uses_minute_bucket() -> None:
    base = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    same_bucket = event_fingerprint("kuma", None, "down", "Mail offline", base + timedelta(seconds=10))
    assert (
        same_bucket
        == event_fingerprint("kuma", None, "down", "Mail offline", base + timedelta(seconds=50))
    )
    other_bucket = event_fingerprint("kuma", None, "down", "Mail offline", base + timedelta(minutes=2))
    assert same_bucket != other_bucket
    different_source = event_fingerprint("sonstiges", None, "down", "Mail offline", base)
    assert same_bucket != different_source


def test_normalize_event_from_raw_payload() -> None:
    event = normalize_event(
        source="truenas",
        raw={"id": 7, "type": "zfs.pool.scan", "severity": "warning", "message": "Scrub found 3 errors"},
        occurred_at=datetime(2026, 11, 9, 10, 0, tzinfo=UTC),
        resource=ResourceRef(resource_type="pool", external_id="backup", name="backup"),
    )
    assert event.source_event_id == "7"
    assert event.event_type == "zfs.pool.scan"
    assert event.severity is EventSeverity.WARNING
    assert event.message == "Scrub found 3 errors"
    assert event.status is AlertStatus.UNKNOWN  # kein Status im Payload
    assert event.resource is not None
    assert event.resource.external_id == "backup"
    assert event.occurred_at.tzinfo is not None
    assert event.received_at.tzinfo is not None


def test_normalize_event_defaults() -> None:
    event = normalize_event(
        source="loki",
        raw={"message": "disk pressure"},
        occurred_at=datetime(2026, 11, 9, 10, 0, tzinfo=UTC),
    )
    assert event.event_type == "unknown"
    assert event.severity is EventSeverity.WARNING
    assert event.resource is None


def test_deduplicator_marks_duplicates() -> None:
    dedup = EventDeduplicator()
    ts = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    first = normalize_event(source="s", raw={"id": "1"}, occurred_at=ts)
    second = normalize_event(source="s", raw={"id": "1"}, occurred_at=ts)
    assert dedup.is_new(first) is True
    assert dedup.is_new(second) is False
    assert len(dedup) == 1


def test_deduplicator_lru_eviction() -> None:
    dedup = EventDeduplicator(max_entries=2)
    ts = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    e1 = normalize_event(source="s", raw={"id": "1"}, occurred_at=ts)
    e2 = normalize_event(source="s", raw={"id": "2"}, occurred_at=ts)
    e3 = normalize_event(source="s", raw={"id": "3"}, occurred_at=ts)
    dedup.is_new(e1)
    dedup.is_new(e2)
    assert len(dedup) == 2
    dedup.is_new(e3)  # evictiert e1 (LRU)
    assert len(dedup) == 2
    assert dedup.is_new(e1) is True  # e1 ist evictiert => neu
    assert dedup.is_new(e3) is False  # e3 weiterhin bekannt


def test_deduplicator_requires_positive_max() -> None:
    with pytest.raises(ValueError):
        EventDeduplicator(max_entries=0)
