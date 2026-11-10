"""SecretsProvider-Implementierung (frozen, R0).

Die einzige R0-Implementierung loest Referenzen aus der Prozess-Umgebung.
In Produktion werden die Variablen aus der geschuetzten Datei
``/etc/hcc/secrets.env`` (0640, nur Service-Gruppe) in die Unit geladen
(siehe deploy/systemd/hcc-api.service).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

# Nur simple, administrative Namen — verhindert Pfade/Sonderkonstruktionen
_SECRET_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")


class InvalidSecretRefError(ValueError):
    pass


class EnvSecretsProvider:
    """Loest Secret-Referenzen aus einer Environment-Mapping (default: os.environ)."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ: Mapping[str, str] = os.environ if environ is None else environ

    def get(self, name: str) -> str | None:
        if not _SECRET_NAME_RE.match(name):
            raise InvalidSecretRefError(f"Ungueltige Secret-Referenz: {name!r}")
        return self._environ.get(name)
