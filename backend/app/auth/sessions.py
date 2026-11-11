"""Serverseitige Session-Verwaltung (frozen Semantik, R0).

- Token: 32 Zufallsbytes als Hex (64 Zeichen), rohes Token nur im Cookie.
- Persistiert wird ausschließlich der SHA-256-Hash.
- Absolute Lifetime: ``session_ttl_seconds`` (Standard 12 h).
- Revocation beim Logout und (spaeter) beim Passwortwechsel.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.mixins import utcnow
from app.models.sessions import UserSession
from app.models.users import User


@dataclass(frozen=True)
class SessionCreated:
    raw_token: str
    expires_at: datetime


def _as_aware(value: datetime) -> datetime:
    """SQLite liefert naive Datetimes; fuer Vergleiche UTC-Zuordnung erzwingen.

    PostgreSQL liefert bereits tz-aware — dort no-op.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SessionService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @staticmethod
    def _token_hash(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def create(
        self,
        db: Session,
        user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> SessionCreated:
        # Nebenbei aufgeraeumt: abgelaufene/widerufene Sessions der Tabelle
        # loesen, damit user_sessions nicht unbeschrankt waechst.
        self.purge_expired(db)

        raw_token = secrets.token_hex(32)
        now = utcnow()
        expires_at = now + timedelta(seconds=self._settings.session_ttl_seconds)
        db.add(
            UserSession(
                token_hash=self._token_hash(raw_token),
                user_id=user_id,
                ip_address=(ip_address or "")[:64] or None,
                user_agent=(user_agent or "")[:256] or None,
                created_at=now,
                expires_at=expires_at,
                last_seen_at=now,
            )
        )
        db.flush()
        return SessionCreated(raw_token=raw_token, expires_at=expires_at)

    def resolve(self, db: Session, raw_token: str) -> User | None:
        """Liefert den User der gueltigen Session; sonst None (abgelaufen/
        widerrufen/ungenau)."""
        if not raw_token:
            return None
        session = db.scalar(select(UserSession).where(UserSession.token_hash == self._token_hash(raw_token)))
        if session is None or session.revoked_at is not None:
            return None
        if _as_aware(session.expires_at) < utcnow():
            return None
        session.last_seen_at = utcnow()
        return db.get(User, session.user_id)

    def revoke(self, db: Session, raw_token: str) -> None:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == self._token_hash(raw_token)))
        if session is not None and session.revoked_at is None:
            session.revoked_at = utcnow()
            db.flush()

    def revoke_all_for_user(self, db: Session, user_id: uuid.UUID) -> int:
        """Widerruft ALLE aktiven Sessions eines Users.

        Wird beim Passwortwechsel und bei Deaktivierung aufgerufen, damit
        bisher ausgegebene Cookies sofort wirkungslos werden.
        Liefert die Anzahl der widerrufenen Sessions.
        """
        result = db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        db.flush()
        return result.rowcount or 0

    def purge_expired(self, db: Session) -> int:
        """Entfernt abgelaufene oder widerrufene Session-Rows (Ruecklauf).

        Liefert die Anzahl der geloeschten Rows. Kann periodisch oder
        nebenbei (z. B. beim Anlegen neuer Sessions) aufgerufen werden.
        """
        now = utcnow()
        result = db.execute(
            delete(UserSession).where(or_(UserSession.expires_at < now, UserSession.revoked_at.is_not(None)))
        )
        db.flush()
        return result.rowcount or 0
