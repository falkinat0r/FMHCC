"""Auth-Contract (frozen, R0).

Semantik:
- Login: JSON, serverseitige Session, Cookies ``hcc_session`` (HttpOnly) und
  ``hcc_csrf`` (nicht HttpOnly, fuer Double-Submit-CSRF im Request-Header
  ``X-CSRF-Token``).
- Bootstrap: einmalig, nur solange keine User existieren, nur mit
  uebergebenem Bootstrap-Token (konstanter Zeitabgleich).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.users import Role


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    message: str
    session_expires_at: datetime


class LogoutResponse(BaseModel):
    message: str


class BootstrapRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    password: str = Field(min_length=10, max_length=200)
    token: str = Field(min_length=16, max_length=256, description="HCC_BOOTSTRAP_TOKEN (einmalig)")


class BootstrapResponse(BaseModel):
    username: str
    message: str


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str | None = None
    role: Role
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None = None
