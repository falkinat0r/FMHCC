"""Health-/Readiness-Endpoints (frozen)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.contracts.health import HealthCheck, HealthStatus, LiveHealthResponse, ReadyHealthResponse
from app.errors import SERVICE_NAME

router = APIRouter(prefix="/health")

# Migration-Head(s) aus der Alembic-Skriptbasis (nur fuer PostgreSQL-Pruefung).
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"
_alembic_heads: set[str] | None = None

_STATUS_RANK = {HealthStatus.OK: 0, HealthStatus.DEGRADED: 1, HealthStatus.UNAVAILABLE: 2}


def _alembic_heads_cached() -> set[str]:
    global _alembic_heads
    if _alembic_heads is None:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(_ALEMBIC_INI))
        cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
        _alembic_heads = set(ScriptDirectory.from_config(cfg).get_heads())
    return _alembic_heads


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


def _worst(status: HealthStatus, other: HealthStatus) -> HealthStatus:
    return status if _STATUS_RANK[status] >= _STATUS_RANK[other] else other


@router.get("/ready", response_model=ReadyHealthResponse)
def ready(request: Request) -> Response:
    """Readiness: API + Datenbank. HTTP 503, wenn nicht bereit."""
    # R1: Bei PostgreSQL-Datenbanken wird zusatzlich der Migration-Status
    # geprueft (alembic_version vs. Repository-Head). Das aendert weder
    # Response-Shape noch den eingefrorenen Contract.
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

    # Migration-Status nur bei PostgreSQL (Produktion): in Tests/Entwicklung
    # (SQLite) existiert alembic_version nicht und waere ein falscher Alarm.
    settings = request.app.state.settings
    if status is HealthStatus.OK and str(settings.database_url).startswith("postgresql"):
        start = time.perf_counter()
        try:
            factory = request.app.state.session_factory
            db = factory()
            try:
                try:
                    version = db.execute(text("SELECT version_num FROM alembic_version")).scalars().first()
                except SQLAlchemyError as exc:
                    # "no such table"/"relation does not exist" => nicht
                    # migriert (degraded); andere DB-Fehler => unavailable.
                    if "alembic_version" not in str(exc):
                        raise
                    version = None
            finally:
                db.close()
            duration_ms = (time.perf_counter() - start) * 1000
            if version is None:
                check = HealthCheck(
                    name="migration",
                    status=HealthStatus.DEGRADED,
                    message="alembic_version fehlt — Datenbank nicht migriert",
                    duration_ms=round(duration_ms, 3),
                )
            elif version not in _alembic_heads_cached():
                check = HealthCheck(
                    name="migration",
                    status=HealthStatus.DEGRADED,
                    message="Migration-Stand weicht vom Repository-Head ab",
                    duration_ms=round(duration_ms, 3),
                )
            else:
                check = HealthCheck(name="migration", status=HealthStatus.OK, duration_ms=round(duration_ms, 3))
        except SQLAlchemyError:
            check = HealthCheck(
                name="migration",
                status=HealthStatus.UNAVAILABLE,
                message="Migration-Zustand nicht bestimmbar",
                duration_ms=round((time.perf_counter() - start) * 1000, 3),
            )
        checks.append(check)
        status = _worst(status, check.status)

    body = ReadyHealthResponse(status=status, checks=checks, time_utc=_now_utc())
    if status is HealthStatus.OK:
        return Response(content=body.model_dump_json(), media_type="application/json", status_code=200)
    return JSONResponse(status_code=503, content=body.model_dump(mode="json"))
