"""Initial HCC schema (R0 Foundation)

Revision ID: 0001
Revises:
Create Date: 2026-11-09

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------------- users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
        sa.CheckConstraint("role IN ('viewer', 'operator', 'admin')", name=op.f("ck_users_role")),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=False)

    # ------------------------------------------------------------ user_sessions
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_sessions_user_id_users"), ondelete="CASCADE"
        ),
    )
    op.create_index(op.f("ix_user_sessions_token_hash"), "user_sessions", ["token_hash"], unique=False)
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"], unique=False)

    # ---------------------------------------------------------- integrations
    op.create_table(
        "integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("adapter", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("secret_ref", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integrations")),
        sa.UniqueConstraint("integration_id", name=op.f("uq_integrations_integration_id")),
        sa.CheckConstraint(
            "adapter IN ('proxmox', 'truenas', 'pihole', 'tailscale', 'docker', "
            "'monitoring', 'homeassistant', 'unknown')",
            name=op.f("ck_integrations_adapter"),
        ),
        sa.CheckConstraint(
            "status IN ('not_configured', 'configured', 'error', 'disabled')",
            name=op.f("ck_integrations_status"),
        ),
    )
    op.create_index(op.f("ix_integrations_integration_id"), "integrations", ["integration_id"], unique=False)

    # ------------------------------------------------------------ resources
    op.create_table(
        "resources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resources")),
        sa.UniqueConstraint(
            "integration_id", "resource_type", "external_id", name="uq_resources_resource_identity"
        ),
        sa.CheckConstraint(
            "resource_type IN ('host', 'node', 'vm', 'lxc', 'container', 'pool', 'dataset', "
            "'tailnet_node', 'dns_stats', 'dashboard', 'other')",
            name=op.f("ck_resources_resource_type"),
        ),
        sa.CheckConstraint(
            "status IN ('healthy', 'degraded', 'down', 'unknown', 'not_configured')",
            name=op.f("ck_resources_status"),
        ),
        sa.CheckConstraint("source IN ('api', 'manual', 'inferred')", name=op.f("ck_resources_source")),
        sa.ForeignKeyConstraint(
            ["integration_id"], ["integrations.id"], name=op.f("fk_resources_integration_id_integrations"), ondelete="CASCADE"
        ),
    )
    op.create_index(op.f("ix_resources_integration_id"), "resources", ["integration_id"], unique=False)
    op.create_index(op.f("ix_resources_resource_type"), "resources", ["resource_type"], unique=False)
    op.create_index(op.f("ix_resources_status"), "resources", ["status"], unique=False)
    op.create_index(op.f("ix_resources_last_seen_at"), "resources", ["last_seen_at"], unique=False)

    # ---------------------------------------------------- resource_relations
    op.create_table(
        "resource_relations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_resource_id", sa.Uuid(), nullable=False),
        sa.Column("target_resource_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("evidence", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=256), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_relations")),
        sa.UniqueConstraint(
            "source_resource_id", "target_resource_id", "relation_type",
            name="uq_resource_relations_relation_identity",
        ),
        sa.CheckConstraint("evidence IN ('api', 'manual', 'inferred')", name=op.f("ck_resource_relations_evidence")),
        sa.ForeignKeyConstraint(
            ["source_resource_id"],
            ["resources.id"],
            name=op.f("fk_resource_relations_source_resource_id_resources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_resource_id"],
            ["resources.id"],
            name=op.f("fk_resource_relations_target_resource_id_resources"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_resource_relations_source_resource_id"), "resource_relations", ["source_resource_id"], unique=False
    )
    op.create_index(
        op.f("ix_resource_relations_target_resource_id"), "resource_relations", ["target_resource_id"], unique=False
    )

    # ----------------------------------------------------------- action_jobs
    op.create_table(
        "action_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("external_resource_id", sa.String(length=128), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_jobs")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_action_jobs_idempotency_key")),
        sa.CheckConstraint("action IN ('start', 'shutdown', 'reboot')", name=op.f("ck_action_jobs_action")),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_action_jobs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"], ["integrations.id"], name=op.f("fk_action_jobs_integration_id_integrations")
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], name=op.f("fk_action_jobs_requested_by_users")),
    )
    op.create_index(op.f("ix_action_jobs_idempotency_key"), "action_jobs", ["idempotency_key"], unique=False)
    op.create_index(op.f("ix_action_jobs_integration_id"), "action_jobs", ["integration_id"], unique=False)
    op.create_index(op.f("ix_action_jobs_requested_by"), "action_jobs", ["requested_by"], unique=False)
    op.create_index(op.f("ix_action_jobs_status"), "action_jobs", ["status"], unique=False)

    # ---------------------------------------------------------- audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=True),
        sa.Column("resource_type", sa.String(length=32), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_audit_events_user_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name=op.f("fk_audit_events_integration_id_integrations"),
            ondelete="SET NULL",
        ),
    )
    op.create_index(op.f("ix_audit_events_username"), "audit_events", ["username"], unique=False)
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"], unique=False)
    op.create_index(op.f("ix_audit_events_created_at"), "audit_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_created_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_action"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_username"), table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index(op.f("ix_action_jobs_status"), table_name="action_jobs")
    op.drop_index(op.f("ix_action_jobs_requested_by"), table_name="action_jobs")
    op.drop_index(op.f("ix_action_jobs_integration_id"), table_name="action_jobs")
    op.drop_index(op.f("ix_action_jobs_idempotency_key"), table_name="action_jobs")
    op.drop_table("action_jobs")

    op.drop_index(op.f("ix_resource_relations_target_resource_id"), table_name="resource_relations")
    op.drop_index(op.f("ix_resource_relations_source_resource_id"), table_name="resource_relations")
    op.drop_table("resource_relations")

    op.drop_index(op.f("ix_resources_last_seen_at"), table_name="resources")
    op.drop_index(op.f("ix_resources_status"), table_name="resources")
    op.drop_index(op.f("ix_resources_resource_type"), table_name="resources")
    op.drop_index(op.f("ix_resources_integration_id"), table_name="resources")
    op.drop_table("resources")

    op.drop_index(op.f("ix_integrations_integration_id"), table_name="integrations")
    op.drop_table("integrations")

    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_token_hash"), table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
