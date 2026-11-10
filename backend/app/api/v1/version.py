"""Version-Endpoint (frozen)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import RELEASE, __version__
from app.contracts.version import VersionResponse
from app.errors import SERVICE_NAME

router = APIRouter()


@router.get("/version", response_model=VersionResponse)
def version(request: Request) -> VersionResponse:
    settings = request.app.state.settings
    return VersionResponse(
        name=SERVICE_NAME,
        version=__version__,
        release=RELEASE,
        commit=settings.git_commit,
    )
