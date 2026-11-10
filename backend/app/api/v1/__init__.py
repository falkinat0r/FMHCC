"""API v1 — Router-Aggregation (frozen Routenplan, R0)."""

from fastapi import APIRouter

from app.api.v1 import audit, auth, health, integrations, resources, users, version

api_v1 = APIRouter()
api_v1.include_router(health.router, tags=["health"])
api_v1.include_router(version.router, tags=["version"])
api_v1.include_router(auth.router, tags=["auth"])
api_v1.include_router(users.router, tags=["users"])
api_v1.include_router(integrations.router, tags=["integrations"])
api_v1.include_router(resources.router, tags=["resources"])
api_v1.include_router(audit.router, tags=["audit"])

__all__ = ["api_v1"]
