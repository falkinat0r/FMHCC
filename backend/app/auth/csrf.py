"""CSRF-Schutz (Double-Submit-Cookie) — Middleware (frozen Semantik, R0).

Regeln:
- Nur fuer state-aendernde Methoden (POST/PUT/PATCH/DELETE) unter /api/v1/.
- Ausnahmen: /auth/login und /auth/bootstrap (es existiert noch keine Session).
- Es muss eine Session vorhanden sein UND der Request-Header ``X-CSRF-Token``
  muss den Wert des CSRF-Cookies exakt matchen (konstanter Zeitabgleich).
- Fehlschlag => HTTP 403 mit Error-Envelope.

Hinweis: Die Middleware liegt AEUSSERHALB des Exception-Handlers, daher wird
die Envelope hier direkt als JSONResponse gebaut (kein Raise).
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import Settings

CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
EXEMPT_PATHS = frozenset({"/api/v1/auth/login", "/api/v1/auth/bootstrap"})


def _envelope(request: Request) -> dict:
    return {
        "error": {
            "code": "forbidden",
            "message": "CSRF-Pruefung fehlgeschlagen",
            "details": None,
            "request_id": str(getattr(request.state, "request_id", "unknown")),
        }
    }


class CsrfMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.method not in SAFE_METHODS
            and request.url.path.startswith("/api/v1/")
            and request.url.path not in EXEMPT_PATHS
        ):
            session_cookie = request.cookies.get(self._settings.session_cookie_name, "")
            csrf_cookie = request.cookies.get(self._settings.csrf_cookie_name, "")
            header = request.headers.get(CSRF_HEADER, "")
            if (
                not session_cookie
                or not csrf_cookie
                or not header
                or not hmac.compare_digest(header, csrf_cookie)
            ):
                return JSONResponse(status_code=403, content=_envelope(request))
        return await call_next(request)
