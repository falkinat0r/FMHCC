"""Health-/Readiness-Endpoints (frozen)."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.contracts.health import HealthCheck, HealthStatus, LiveHealthResponse, ReadyHealthResponse
from app.errors import SERVICE_NAME

router = APIRouter(prefix="/health")


def _now_utc() -> datetime:
    return datetime.now(UTC)


@router.get("/live", response_model=LiveHealthResponse)
def live() -> LiveHealthResponse:
    """Live: Process/API erreichbar (fuer systemd liveness)."""
    return LiveHealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=__version__,
        time_utc=_now_utc(),
    )


@router.get("/ready", response_model=ReadyHealthResponse)
def ready(request: Request) -> Response:
    """Readiness: API + Datenbank. HTTP 503, wenn nicht bereit."""
    checks: list[HealthCheck] = []
    status = HealthStatus.OK

    start = time.perf_counter()
    try:
        factory = request.app.state.session_factory
        db = factory()
        try:
            db.execute(text("SELECT 1"))
            db.commit()
        finally:
            db.close()
        duration_ms = (time.perf_counter() - start) * 1000
        checks.append(HealthCheck(name="database", status=HealthStatus.OK, duration_ms=round(duration_ms, 3)))
    except SQLAlchemyError:
        duration_ms = (time.perf_counter() - start) * 1000
        checks.append(
            HealthCheck(
                name="database",
                status=HealthStatus.UNAVAILABLE,
                message="Datenbank nicht erreichbar",
                duration_ms=round(duration_ms, 3),
            )
        )
        status = HealthStatus.UNAVAILABLE

    body = ReadyHealthResponse(status=status, checks=checks, time_utc=_now_utc())
    if status is HealthStatus.OK:
        return Response(content=body.model_dump_json(), media_type="application/json", status_code=200)
    return JSONResponse(status_code=503, content=body.model_dump(mode="json"))
