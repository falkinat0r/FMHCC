"""Passwort-Hashing mit Argon2id (verbindlich fuer HCC)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id-Standardparameter; Parameter wandern in den Hash mit.
_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """True nur bei exaktem Match; False bei falschem Passwort oder
    ungueltigem Hash-Format (keine Exception ueber die API)."""
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
