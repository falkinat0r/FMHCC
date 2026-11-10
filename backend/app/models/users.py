"""User-Modell und Rollen (RBAC)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, enum_values
from app.models.mixins import TimestampMixin


class Role(StrEnum):
    """Berechtigungsstufen (frozen): viewer < operator < admin."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Enum(native_enum=False, create_constraint=True): VARCHAR + CHECK,
    # liefert beim Lesen echte Role-Instanzen. CHECK-Name ck_users_role
    # entsteht ueber die Naming-Convention (ck_<table>_<constraint_name>).
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            name="role",
            native_enum=False,
            length=16,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=Role.VIEWER,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} role={self.role}>"
