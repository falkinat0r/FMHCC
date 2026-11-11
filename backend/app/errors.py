"""Einheitliche Error-Envelope und Exception-Handler.

Contract (eingefroren, R0):
    {
      "error": {
        "code": "<machine-readable>",
        "message": "<menschenlesbar, keine Secrets/Stacktraces>",
        "details": {...} | null,
        "request_id": "<uuid>"
      }
    }

Zustandsbeobachtungen im Payload sind immer UTC ISO-8601.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import __version__  # noqa: F401  (Version wird im OpenAPI-Dokument verwendet)

SERVICE_NAME = "hcc-api"
logger = logging.getLogger("hcc.api")


class ErrorCode(StrEnum):
    """Stabile, maschinenlesbare Fehler-Codes (frozen Contract)."""

    VALIDATION_ERROR = "validation_error"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    NOT_CONFIGURED = "not_configured"
    NOT_IMPLEMENTED = "not_implemented"
    ADAPTER_ERROR = "adapter_error"
    INTERNAL_ERROR = "internal_error"


# HTTP-Status -> stabiler Code (frozen Mapping)
_STATUS_CODE_MAP: dict[int, tuple[ErrorCode, str]] = {
    400: (ErrorCode.VALIDATION_ERROR, "Ungueltige Anfrage"),
    401: (ErrorCode.UNAUTHENTICATED, "Nicht authentifiziert"),
    403: (ErrorCode.FORBIDDEN, "Keine Berechtigung"),
    404: (ErrorCode.NOT_FOUND, "Ressource nicht gefunden"),
    405: (ErrorCode.NOT_FOUND, "Methode fuer diese Ressource nicht erlaubt"),
    409: (ErrorCode.CONFLICT, "Konflikt"),
    422: (ErrorCode.VALIDATION_ERROR, "Request-Validierung fehlgeschlagen"),
    429: (ErrorCode.RATE_LIMITED, "Zu viele Anfragen, bitte warten"),
    501: (ErrorCode.NOT_IMPLEMENTED, "Nicht implementiert"),
    503: (ErrorCode.INTERNAL_ERROR, "Dienst aktuell nicht bereit"),
}


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    details: Any | None = None
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    """Interne Domain-Fehler mit stabilem Code und HTTP-Status."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def http_error(
    status_code: int,
    code: ErrorCode,
    message: str,
    details: Any | None = None,
) -> ApiError:
    """Konstruktor-Helfer fuer Routen und Services."""
    return ApiError(code=code, message=message, status_code=status_code, details=details)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _envelope(request: Request, code: ErrorCode, message: str, details: Any | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code.value,
            "message": message,
            "details": details if details is not None else None,
            "request_id": _request_id(request),
        }
    }


class UnhandledErrorMiddleware:
    """Aeuesserste App-Middleware: unbehaltene Exceptions => 500-Error-Envelope.

    Starlette >= 1.x re-raist ServerErrors selbst nach dem Absenden einer
    Response (ServerErrorMiddleware) — ohne diese Schicht ist das
    500-Envelope im TestClient unbestimmt. Hier wird die Envelope
    deterministisch erzeugt, in TestClient, uvicorn und jedem anderen
    ASGI-Server. Die Stacktrace landet ausschliesslich in den
    serverseitigen Logs, nie in der API-Antwort.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def _send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:
            if response_started:
                # Antwort hat bereits begonnen — nichts mehr zu senden.
                raise
            request = Request(scope)
            logger.exception(
                "unhandled error on %s %s", scope.get("method", "?"), scope.get("path", "?"), exc_info=exc
            )
            response = JSONResponse(
                status_code=500,
                content=_envelope(request, ErrorCode.INTERNAL_ERROR, "Unerwarteter Serverfehler"),
            )
            await response(scope, receive, _send)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope(
                request,
                ErrorCode.VALIDATION_ERROR,
                "Request-Validierung fehlgeschlagen",
                details={"errors": [
                    {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
                    for e in exc.errors()
                ]},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, default_message = _STATUS_CODE_MAP.get(exc.status_code, (ErrorCode.INTERNAL_ERROR, "Fehler"))
        message = exc.detail if isinstance(exc.detail, str) and exc.detail else default_message
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(
                request,
                code,
                message,
                details=exc.headers and None,
            ),
        )

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        headers = {"Retry-After": "60"} if exc.status_code == 429 else None
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(request, exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        # Stacktrace nur in serverseitige Logs — nie in die API-Antwort.
        logger.exception("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_envelope(request, ErrorCode.INTERNAL_ERROR, "Unerwarteter Serverfehler"),
        )
