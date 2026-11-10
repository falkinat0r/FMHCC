"""Auth-Paket (serverseitige Sessions, Argon2id, RBAC, CSRF, Bootstrap).

Eigentuemer ab R1: Agent 1 (backend-auth) — die R0-Basis ist eingefroren.
"""

from app.auth.bootstrap import create_bootstrap_admin
from app.auth.csrf import CSRF_HEADER, CsrfMiddleware
from app.auth.hashing import hash_password, verify_password
from app.auth.rate_limit import SlidingWindowLimiter
from app.auth.rbac import PERMISSIONS, ROLE_LEVELS, has_permission, require_permission
from app.auth.sessions import SessionCreated, SessionService

__all__ = [
    "CSRF_HEADER",
    "CsrfMiddleware",
    "PERMISSIONS",
    "ROLE_LEVELS",
    "SessionCreated",
    "SessionService",
    "SlidingWindowLimiter",
    "create_bootstrap_admin",
    "hash_password",
    "has_permission",
    "require_permission",
    "verify_password",
]
