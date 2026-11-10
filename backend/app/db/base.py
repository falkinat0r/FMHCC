"""ORM-Base mit deterministischen Constraint-Namen (fuer saubere Alembic-Migrationen)."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Deterministische Naming-Convention -> stabile Constraint-Namen in Migrationen
NAMING_CONVENTION = {
    # Tabelle explizit im Namen — Indexnamen sind database-global eindeutig
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


def enum_values(enum_cls):
    """Persistiert .value (nicht .name) der StrEnum-Member.

    Damit stimmen die VARCHAR-Werte in der Datenbank mit den
    Alembic-Migrationen und den API-Contracts ueberein.
    """
    return [member.value for member in enum_cls]


class Base(DeclarativeBase):
    metadata = metadata
