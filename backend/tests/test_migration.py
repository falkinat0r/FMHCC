"""Migration-Tests: Alembic-Initialmigration muss gegen SQLite laufen (R0).

Produktion laeuft gegen PostgreSQL; der SQLite-Check garantiert, dass die
Migration syntaktisch valide, komplett und reversibel ist.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


@pytest.fixture()
def migrated_sqlite(tmp_path):
    db_path = tmp_path / "migration_test.sqlite3"
    url = f"sqlite:///{db_path}"
    os.environ["HCC_DATABASE_URL"] = url
    try:
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(cfg, "head")
        yield url
    finally:
        os.environ.pop("HCC_DATABASE_URL", None)


def test_upgrade_head_creates_all_tables(migrated_sqlite) -> None:
    engine = create_engine(migrated_sqlite)
    try:
        tables = set(inspect(engine).get_table_names())
        expected = {
            "users",
            "user_sessions",
            "integrations",
            "resources",
            "resource_relations",
            "action_jobs",
            "audit_events",
        }
        assert expected <= tables, f"Fehlende Tabellen: {expected - tables}"
    finally:
        engine.dispose()


def test_downgrade_removes_tables(migrated_sqlite, tmp_path) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.downgrade(cfg, "base")
    engine = create_engine(migrated_sqlite)
    try:
        tables = set(inspect(engine).get_table_names())
        # alembic_version bleibt nach dem Downgrade bestehen (Alembic-Verhalten),
        # alle fachlichen Tabellen muessen weg sein.
        assert tables <= {"alembic_version"}, f"Nach Downgrade bleiben Tabellen: {tables}"
    finally:
        engine.dispose()


def test_alembic_current_reports_revision(migrated_sqlite) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    from alembic.runtime.migration import MigrationContext

    engine = create_engine(migrated_sqlite)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert context.get_current_revision() == "0001"
    finally:
        engine.dispose()
