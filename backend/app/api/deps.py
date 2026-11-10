"""API-Dependencies (Auth-Context, RBAC).

``request.state.current_user`` wird einmalig pro Request aus dem
Session-Cookie geloest (StatefulMiddleware) und von den Routen genutzt.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.auth.sessions import SessionService
from app.config import Settings


class SessionContextMiddleware(BaseHTTPMiddleware):
    """Loest das Session-Cookie und legt ``request.state.current_user``."""

    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings
        self._sessions = SessionService(settings)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.current_user = None
        raw_token = request.cookies.get(self._settings.session_cookie_name, "")
        if raw_token:
            # Session-Lesen ist ein schneller PK-Lookup; im Request-Context
            # wird die App-Session-Factory verwendet.
            factory = request.app.state.session_factory
            db = factory()
            try:
                user = self._sessions.resolve(db, raw_token)
                db.commit()
            finally:
                db.close()
            request.state.current_user = user
        return await call_next(request)
