"""PostgreSQL-Verifikation (R1, Agent 1: Backend Core).

Produktion laeuft gegen PostgreSQL. Zwei Pruefungen:

1. **Offline-DDL (ohne Server):** Die eingefrorene Initialmigration
   (``0001_initial.py``, aus ``backend/alembic/versions/`` — hier nur
   gelesen, nie geaendert) wird gegen das PostgreSQL-Dialekt als SQL
   gerendert. Damit wird ohne Live-Server geprueft, dass das DDL
   gueltiges PostgreSQL ist und alle Tabellen, benannten Constraints und
   Foreign Keys korrekt entstehen.

   Hinweis: Die geteilte ``backend/alembic/env.py`` ist im Offline-Modus
   defekt (uebergibt ``sqlalchemy.url`` nicht als ``url`` an
   MigrationContext; R0 nur im Online-Modus getestet). Da
   ``backend/alembic/**`` gemeinsamer Bereich ist, wird das hier nicht
   stillschweigend repariert, sondern als Vorschlag dokumentiert:
   ``docs/proposals/backend-alembic-offline-sql.md``. Der Test nutzt daher
   eine Test-Env (tmp), die die ECHTEN Migrationsskripte unveraendert
   ausfuehrt.

2. **Live (optional):** Falls ``HCC_TEST_DATABASE_URL`` auf ein erreichbares
   PostgreSQL zeigt, wird die Migration wirklich ausgefuehrt, die Tabellen
   inspiziert und ein User-Roundtrip gespielt. Andernfalls wird der Test
   sauber gependet.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"

EXPECTED_TABLES = {
    "users",
    "user_sessions",
    "integrations",
    "resources",
    "resource_relations",
    "action_jobs",
    "audit_events",
}

# Benannte Constraints, die in der Initialmigration festgelegt sind und
# identisch zur ORM-Naming-Convention sein muessen.
EXPECTED_CONSTRAINTS = {
    "ck_users_role",
    "ck_integrations_adapter",
    "ck_integrations_status",
    "ck_resources_resource_type",
    "ck_resources_status",
    "ck_resources_source",
    "ck_resource_relations_evidence",
    "ck_action_jobs_action",
    "ck_action_jobs_status",
}

# Minimal-Env nur fuer den Offline-DDL-Test (tmp, kein Einfluss auf Repo).
_TEST_ENV_PY = """
from alembic import context

config = context.config


def run_migrations_offline() -> None:
    url = "postgresql+psycopg://hcc:hcc@127.0.0.1:5432/hcc"
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    raise NotImplementedError("Dieser Test laeuft nur offline.")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"""


def _render_offline_postgres_sql(tmp_path: Path) -> str:
    """Initialmigration als PostgreSQL-SQL rendern (kein Live-Server)."""
    alembic_dir = tmp_path / "alembic_offline"
    alembic_dir.mkdir()
    (alembic_dir / "env.py").write_text(_TEST_ENV_PY, encoding="utf-8")
    shutil.copytree(VERSIONS_DIR, alembic_dir / "versions")

    cfg = Config()
    cfg.set_main_option("script_location", str(alembic_dir))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        command.upgrade(cfg, "head", sql=True)
    return buf.getvalue()


def test_postgres_offline_ddl_creates_all_tables(tmp_path: Path) -> None:
    sql = _render_offline_postgres_sql(tmp_path)
    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE {table}" in sql, f"Fehlende CREATE TABLE {table} im PostgreSQL-DDL"


def test_postgres_offline_ddl_has_named_check_constraints(tmp_path: Path) -> None:
    sql = _render_offline_postgres_sql(tmp_path)
    for constraint in EXPECTED_CONSTRAINTS:
        assert constraint in sql, f"Fehlender benannter Constraint {constraint} im PostgreSQL-DDL"


def test_postgres_offline_ddl_has_foreign_keys(tmp_path: Path) -> None:
    sql = _render_offline_postgres_sql(tmp_path)
    # Kernaender FKs: Sessions->Users, Resources->Integrations,
    # ActionJobs->Users/Integrations, Audit->Users/Integrations (SET NULL).
    assert "REFERENCES users" in sql
    assert "REFERENCES integrations" in sql
    assert "ON DELETE CASCADE" in sql
    assert "ON DELETE SET NULL" in sql


def test_postgres_offline_ddl_uses_uuid_type(tmp_path: Path) -> None:
    sql = _render_offline_postgres_sql(tmp_path)
    # sa.Uuid() rendert im PostgreSQL-Dialekt als UUID.
    assert "UUID" in sql.upper()


# ---------------------------------------------------------------------------
# Live-Pruefung (nur, wenn ein erreichbares PostgreSQL vorhanden ist)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    os.environ.get("HCC_TEST_DATABASE_URL") is None,
    reason="HCC_TEST_DATABASE_URL nicht gesetzt — kein erreichbares PostgreSQL in dieser Umgebung",
)
def test_postgresql_live_migration_roundtrip() -> None:
    url = os.environ["HCC_TEST_DATABASE_URL"]
    os.environ["HCC_DATABASE_URL"] = url
    try:
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        try:
            tables = set(inspect(engine).get_table_names())
            assert tables >= EXPECTED_TABLES, f"Fehlende Tabellen: {EXPECTED_TABLES - tables}"

            # User-Roundtrip mit Argon2-Hash (Produktions-Semantik)
            import uuid as _uuid

            from app.auth.hashing import hash_password
            from app.models.users import Role

            uid = _uuid.uuid4()
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO users (id, username, role, password_hash, is_active, must_change_password, created_at, updated_at) "
                        "VALUES (:id, :u, :r, :h, true, true, now(), now())"
                    ),
                    {"id": uid, "u": "pg-live", "r": Role.ADMIN.value, "h": hash_password("pg-live-pass-123")},
                )
                row = conn.execute(text("SELECT username, role FROM users WHERE id = :id"), {"id": uid}).one()
                assert row[0] == "pg-live"
                assert row[1] == "admin"
        finally:
            engine.dispose()
    finally:
        os.environ.pop("HCC_DATABASE_URL", None)
