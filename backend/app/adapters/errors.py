"""Adapter-Fehlerhierarchie (frozen, R0).

Jeder Adapter-Fehler traegt einen stabilen ``AdapterState`` und wird so
maschinell in den API-Contract (VerifyStatus / ErrorEnvelope) ueberfuehrbar.
Message-Texte duerfen keine Secrets/URLs mit Token enthalten.
"""

from __future__ import annotations

from app.adapters.base import AdapterState


class AdapterError(Exception):
    """Basisfehler aller Adapter."""

    def __init__(self, message: str, state: AdapterState, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.state = state
        self.details = details or {}


class AdapterConfigError(AdapterError):
    """Konfiguration fehlt oder ist ungueltig."""

    def __init__(self, message: str = "Adapter nicht konfiguriert", details: dict | None = None) -> None:
        super().__init__(message, state=AdapterState.NOT_CONFIGURED, details=details)


class AdapterAuthError(AdapterError):
    """Credentials fehlen, sind ungültig oder Rechte nicht ausreichend."""

    def __init__(self, message: str = "Authentifizierung fehlgeschlagen", details: dict | None = None) -> None:
        super().__init__(message, state=AdapterState.AUTH_FAILED, details=details)


class AdapterUnreachableError(AdapterError):
    """Ziel nicht erreichbar (DNS, Netzwerk, Firewall)."""

    def __init__(self, message: str = "Ziel nicht erreichbar", details: dict | None = None) -> None:
        super().__init__(message, state=AdapterState.UNREACHABLE, details=details)


class AdapterTimeoutError(AdapterError):
    """Timeout innerhalb der konfigurierten Grenze."""

    def __init__(self, message: str = "Zeitueberschreitung", details: dict | None = None) -> None:
        super().__init__(message, state=AdapterState.TIMEOUT, details=details)


class AdapterApiError(AdapterError):
    """API-Antwort mit Fehlerstatus."""

    def __init__(
        self,
        message: str = "API-Fehler",
        http_status: int | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, state=AdapterState.API_ERROR, details=details)
        self.http_status = http_status


class AdapterVersionError(AdapterError):
    """API-Version der Instanz wird nicht unterstuetzt."""

    def __init__(self, message: str = "API-Version nicht unterstuetzt", details: dict | None = None) -> None:
        super().__init__(message, state=AdapterState.VERSION_UNSUPPORTED, details=details)
