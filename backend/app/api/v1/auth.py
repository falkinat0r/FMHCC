"""Auth-Endpoints (frozen Routenplan, R0): bootstrap, login, logout, me.

Cookies:
- ``hcc_session``: HttpOnly, SameSite=Lax, Secure (production), Lifetime = Session-TTL
- ``hcc_csrf``:  nicht HttpOnly (wird im Request-Header X-CSRF-Token gespiegelt)
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.log import record_audit
from app.auth.bootstrap import create_bootstrap_admin
from app.auth.hashing import verify_password
from app.auth.rate_limit import SlidingWindowLimiter
from app.auth.sessions import SessionService
from app.config import Settings
from app.contracts.auth import (
    BootstrapRequest,
    BootstrapResponse,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
)
from app.db.session import get_db
from app.errors import ErrorCode, http_error
from app.models.users import User

router = APIRouter(prefix="/auth")

# Login-Rate-Limit: 10 Versuche pro IP / 60 s (R0-Default, frozen)
_login_limiter = SlidingWindowLimiter(max_calls=10, window_seconds=60)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _sessions(request: Request) -> SessionService:
    return SessionService(_settings(request))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return (request.headers.get("user-agent") or "")[:256] or None


def _csrf_token() -> str:
    return secrets.token_hex(32)


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=201)
def bootstrap(
    payload: BootstrapRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> BootstrapResponse:
    user = create_bootstrap_admin(
        db,
        _settings(request),
        username=payload.username,
        password=payload.password,
        token=payload.token,
    )
    record_audit(db, user=user, action="auth.bootstrap.success", request=request)
    return BootstrapResponse(
        username=user.username,
        message="Initialer Admin angelegt. Passwort vor erster Nutzung aendern.",
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    settings = _settings(request)
    ip = _client_ip(request) or "unknown"

    if not _login_limiter.allow(ip):
        record_audit(db, user=None, action="auth.login.rate_limited", request=request)
        raise http_error(429, ErrorCode.RATE_LIMITED, "Zu viele Anmeldeversuche, bitte kurz warten")

    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(user.password_hash, payload.password):
        record_audit(db, user=user, action="auth.login.failed", request=request)
        raise http_error(401, ErrorCode.UNAUTHENTICATED, "Anmeldedaten ungültig")
    if not user.is_active:
        record_audit(db, user=user, action="auth.login.rejected_inactive", request=request)
        raise http_error(403, ErrorCode.FORBIDDEN, "Konto ist deaktiviert")

    session = _sessions(request).create(db, user.id, ip_address=ip, user_agent=_user_agent(request))
    user.last_login_at = datetime.now(UTC)
    record_audit(db, user=user, action="auth.login.success", request=request)

    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.raw_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=_csrf_token(),
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return LoginResponse(message="Erfolgreich angemeldet", session_expires_at=session.expires_at)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LogoutResponse:
    settings = _settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name, "")
    user = getattr(request.state, "current_user", None)
    if raw_token:
        _sessions(request).revoke(db, raw_token)
        record_audit(db, user=user, action="auth.logout.success", request=request)
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    return LogoutResponse(message="Abgemeldet")


@router.get("/me", response_model=CurrentUserResponse)
def me(request: Request) -> CurrentUserResponse:
    user = getattr(request.state, "current_user", None)
    if user is None or not user.is_active:
        raise http_error(401, ErrorCode.UNAUTHENTICATED, "Anmeldung erforderlich")
    return CurrentUserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
