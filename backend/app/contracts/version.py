"""Version-Contract (frozen, R0)."""

from __future__ import annotations

from pydantic import BaseModel


class VersionResponse(BaseModel):
    name: str
    version: str
    release: str
    commit: str  # 'unknown', wenn nicht bekannt — nie erfunden
