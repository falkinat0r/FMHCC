"""Datenmodell-Tests: User, Session, Integration, Resource-Dedup, Jobs, Audit (R0)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.adapters.base import ResourceRecord
from app.audit.log import record_audit
from app.auth.hashing import hash_password, verify_password
from app.auth.sessions import SessionService
from app.config import Settings
from app.inventory.base import upsert_resources
from app.models.action_jobs import ActionJob, ActionType, JobStatus
from app.models.integrations import Integration, IntegrationStatus
from app.models.resources import Resource, ResourceRelation, ResourceStatus, ResourceType
from app.models.users import Role, User


def _settings() -> Settings:
    return Settings(database_url="sqlite://", bootstrap_token="test-token-0123456789")


def aware(value: datetime) -> datetime:
    """SQLite liefert naive Datetimes — fuer Vergleiche UTC zuordnen."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def test_password_hashing_uses_argon2id() -> None:
    hashed = hash_password("geheim-passwort-123")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "geheim-passwort-123") is True
    assert verify_password(hashed, "anderes-passwort-1") is False
    assert verify_password("kein-gueltiger-hash", "x") is False


def test_session_lifecycle(db) -> None:
    service = SessionService(_settings())
    user = User(username="sess-test", role=Role.VIEWER, password_hash=hash_password("passwort-12345"))
    db.add(user)
    db.flush()

    created = service.create(db, user.id, ip_address="127.0.0.1", user_agent="pytest")
    assert created.raw_token and len(created.raw_token) == 64

    resolved = service.resolve(db, created.raw_token)
    assert resolved is not None and resolved.id == user.id

    service.revoke(db, created.raw_token)
    assert service.resolve(db, created.raw_token) is None


def test_upsert_resources_deduplicates(db) -> None:
    integration = Integration(
        integration_id="proxmox-1",
        name="Proxmox Test",
        adapter="proxmox",
        status=IntegrationStatus.CONFIGURED,
        capabilities={},
    )
    db.add(integration)
    db.flush()

    now = datetime.now(UTC)
    record = ResourceRecord(
        resource_type=ResourceType.VM,
        external_id="101",
        name="atlas",
        status=ResourceStatus.HEALTHY,
        payload={"vcpus": 2},
        observed_at=now,
    )
    first = upsert_resources(db, integration, [record])
    assert first.created == 1 and first.updated == 0

    later = now + timedelta(minutes=5)
    record2 = record.model_copy(update={"observed_at": later, "status": ResourceStatus.DEGRADED})
    second = upsert_resources(db, integration, [record2])
    assert second.created == 0 and second.updated == 1

    rows = db.scalars(select(Resource)).all()
    assert len(rows) == 1
    assert rows[0].status == ResourceStatus.DEGRADED
    assert aware(rows[0].last_seen_at) == later
    assert aware(rows[0].first_seen_at) == now


def test_upsert_creates_relations_with_parent(db) -> None:
    integration = Integration(integration_id="pve-x", name="x", adapter="proxmox", status=IntegrationStatus.CONFIGURED, capabilities={})
    db.add(integration)
    db.flush()
    now = datetime.now(UTC)

    host_record = ResourceRecord(
        resource_type=ResourceType.HOST,
        external_id="node1",
        name="node1",
        status=ResourceStatus.HEALTHY,
        observed_at=now,
    )
    vm_record = ResourceRecord(
        resource_type=ResourceType.VM,
        external_id="101",
        name="atlas",
        status=ResourceStatus.HEALTHY,
        observed_at=now,
        parent_external_id="node1",
        parent_resource_type=ResourceType.HOST,
        relation_type="runs_on",
    )
    # Zuerst Host, dann VM (Parent muss existieren)
    upsert_resources(db, integration, [host_record])
    result = upsert_resources(db, integration, [vm_record])
    assert result.relations_created == 1

    relation = db.scalar(select(ResourceRelation))
    assert relation is not None
    assert relation.relation_type == "runs_on"

    # Wiederholung: keine Duplikate
    again = upsert_resources(db, integration, [vm_record])
    assert again.relations_created == 0
    assert len(db.scalars(select(ResourceRelation)).all()) == 1


def test_action_job_idempotency_key_is_unique(db) -> None:
    integration = Integration(integration_id="pve-y", name="y", adapter="proxmox", status=IntegrationStatus.CONFIGURED, capabilities={})
    user = User(username="jobuser", role=Role.OPERATOR, password_hash=hash_password("passwort-12345"))
    db.add_all([integration, user])
    db.flush()

    db.add(
        ActionJob(
            idempotency_key="idem-1",
            action=ActionType.START,
            integration_id=integration.id,
            external_resource_id="101",
            requested_by=user.id,
            status=JobStatus.PENDING,
            details={},
        )
    )
    db.flush()
    with pytest.raises(IntegrityError):
        db.add(
            ActionJob(
                idempotency_key="idem-1",
                action=ActionType.START,
                integration_id=integration.id,
                external_resource_id="101",
                requested_by=user.id,
                status=JobStatus.PENDING,
                details={},
            )
        )
        db.flush()


def test_audit_details_are_masked(db) -> None:
    user = User(username="audituser", role=Role.ADMIN, password_hash=hash_password("passwort-12345"))
    db.add(user)
    db.flush()
    event = record_audit(
        db,
        user=user,
        action="auth.login.success",
        details={"password": "supersecret-passwort-99", "username": "audituser"},
    )
    db.flush()
    assert event.details["password"] != "supersecret-passwort-99"
    assert "***" in event.details["password"]
    assert event.details["username"] == "audituser"
    assert event.username == "audituser"


def test_user_session_fk_cascades(db) -> None:
    service = SessionService(_settings())
    user = User(username="cascadeuser", role=Role.VIEWER, password_hash=hash_password("passwort-12345"))
    db.add(user)
    db.flush()
    service.create(db, user.id)
    db.flush()
    user_id = user.id
    db.delete(user)
    db.flush()
    from app.models.sessions import UserSession

    assert db.scalar(select(UserSession).where(UserSession.user_id == user_id)) is None
