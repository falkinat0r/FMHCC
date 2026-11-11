"""FastAPI-App-Factory (HCC API).

Bindet:
- Strukturiertes Logging
- Request-Id-Kontext
- Session-Kontext (serverseitige Sessions)
- CSRF-Middleware (Double-Submit-Cookie)
- Einheitliche Error-Envelope
- versionierte API unter /api/v1

Backend bindet ausschließlich auf Loopback (Default 127.0.0.1:8000);
nginx leitet /api/ weiter — siehe deploy/nginx/hcc.conf.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from sqlalchemy import create_engine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app import __version__
from app.api.deps import SessionContextMiddleware
from app.api.v1 import api_v1
from app.auth.csrf import CsrfMiddleware
from app.config import Environment, Settings, get_settings
from app.db.session import build_session_factory
from app.errors import ErrorEnvelope, UnhandledErrorMiddleware, register_exception_handlers
from app.integrations.bootstrap import register_all_adapters
from app.logging_setup import configure_logging, request_id_var


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Erzeugt/übernimmt X-Request-ID und legt sie in request.state + Log-Kontext."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = request_id
        return response


def _build_engine(settings: Settings):
    kwargs: dict = {"pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(settings.database_url, **kwargs)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()
    configure_logging(settings.log_level)

    engine = _build_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    docs_enabled = settings.environment is not Environment.PRODUCTION
    app = FastAPI(
        title="Homelab Control Center API",
        version=__version__,
        description=(
            "Self-hosted Homelab Control Center. Versionierte API unter /api/v1. "
            "Error-Envelope, UTC-Zeitstempel, Paging und RBAC siehe docs/api-contracts.md."
        ),
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs" if docs_enabled else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)

    # R1-Integration: alle in diesem Build enthaltenen Adapter in die
    # Adapter-Registry eintragen (idempotent, nicht-abstuerzend), damit
    # der Verify-Endpunkt real antwortet statt not_implemented.
    # Vorschlag: docs/proposals/agent3-proxmox-core-integration.md (Item 1).
    register_all_adapters()

    register_exception_handlers(app)
    app.include_router(api_v1, prefix="/api/v1")

    # Middleware-Ordung: letztes add_middleware = aeußerste Schicht.
    # Resultierender Stack (außen→innen): RequestID → Session → CSRF →
    # UnhandledError → (Route-Exception-Handler) → Router.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
        )
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(CsrfMiddleware, settings=settings)
    app.add_middleware(SessionContextMiddleware, settings=settings)
    app.add_middleware(RequestIDMiddleware)

    # OpenAPI: Error-Envelope ist ein verbindlicher Contract, wird aber von
    # keiner Route als response_model referenziert. Damit die Envelope im
    # verbindlichen OpenAPI-Dokument mitverifiziert werden kann (Contract-
    # Snapshot-Test), wird sie hier explizit in components.schemas injiziert.
    def _error_envelope_schemas() -> dict[str, dict]:
        probe = FastAPI(title="hcc-probe", version=__version__)

        @probe.get("/__hcc_error_probe__", response_model=ErrorEnvelope)
        def _probe() -> ErrorEnvelope:  # pragma: no cover (nur Schema-Generierung)
            raise AssertionError("unreachable")

        schemas = probe.openapi().get("components", {}).get("schemas", {})
        return {name: schemas[name] for name in ("ErrorEnvelope", "ErrorBody", "ErrorCode") if name in schemas}

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema.setdefault("components", {}).setdefault("schemas", {}).update(_error_envelope_schemas())
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi

    return app


app = create_app()
