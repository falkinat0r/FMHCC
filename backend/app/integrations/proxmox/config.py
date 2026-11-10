"""Proxmox-Adapter-Konfiguration (Agent 3, R1).

Secret-Format (Wert der ``secret_ref``-Umgebungsvariable, NICHT der Name):

    <user>@<realm>!<token-id>=<secret>

Beispiel (klar als Test-Placeholder, kein echtes Secret):

    hcc@pve!hcc-inventory=0123456789abcdef01234789abcdef012345

Proxmox zeigt den Wert nach der Token-Erstellung im genau diesem Format an
(Documentation: "API Tokens" — ``Authorization: PVEAPIToken=user@realm!tokenid=secret``).
Der Wert ist ein Proxmox-API-Token, kein Passwort. Root-Passwoerter werden
von diesem Adapter bewusst nicht unterstuetzt.

Optionen koennen pro Integration ueber ``AdapterConfig.extra`` (nur Strings)
gesetzt werden. Es gilt das Prinzip: TLS-Verifizierung ist Standard;
Abschaltung ist ein explizites, loggefuehrtes Opt-in — niemals Default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.adapters.base import AdapterConfig
from app.adapters.errors import AdapterConfigError

# user@realm!tokenid — realm z. B. 'pam', 'pve', 'ldap'; tokenid ohne '@'/'!'
_TOKEN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+![A-Za-z0-9._-]+$")
# Proxmox-Secrets sind 32 hex-Zeichen; toleranter, aber nicht leer/weich
_SECRET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{15,}$")

# Uebernahme der Proxmox-Dokumentation: mindestens PVE 8 (API api2/json,
# Token-Auth, Cluster-Endpoints). PVE 7 ist EOL und wird nicht unterstuetzt.
MINIMUM_PVE_MAJOR = 8

# Default-Abfragehaeufigkeit: konservativ, Proxmox selbst ratetlimitiert auch
DEFAULT_RATE_LIMIT_PER_SECOND = 5.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class ProxmoxToken:
    """Geparterter API-Token (ID + Secret)."""

    token_id: str  # z. B. 'hcc@pve!hcc-inventory'
    secret: str  # 32 hex-Zeichen


def parse_token(raw: str | None) -> ProxmoxToken:
    """Parse den Secret-Wert ``user@realm!tokenid=secret`` (Fallback ':').

    Wirft ``AdapterConfigError`` (state=not_configured) bei fehlendem oder
    ungueltigem Wert — mit klarer, secret-freier Meldung.
    """
    if raw is None or not raw.strip():
        raise AdapterConfigError("Proxmox-API-Token fehlt (Secret-Variable leer oder nicht gesetzt)")

    candidate = raw.strip()
    token_id, secret = _split_token(candidate)
    if token_id is None or secret is None:
        raise AdapterConfigError(
            "Proxmox-API-Token hat ungueltiges Format; erwartet <user>@<realm>!<token-id>=<secret>"
        )
    if not _TOKEN_ID_RE.match(token_id):
        raise AdapterConfigError("Proxmox-API-Token: Token-ID ('user@realm!tokenid') ist ungueltig")
    if not _SECRET_RE.match(secret):
        raise AdapterConfigError("Proxmox-API-Token: Secret ist ungueltig (leer oder zu kurz)")
    return ProxmoxToken(token_id=token_id, secret=secret)


def _split_token(candidate: str) -> tuple[str | None, str | None]:
    for separator in ("=", ":"):
        index = candidate.rfind(separator)
        if index <= 0 or index == len(candidate) - 1:
            continue
        token_id, secret = candidate[:index].strip(), candidate[index + 1 :].strip()
        if "@" in token_id and "!" in token_id:
            return token_id, secret
    return None, None


@dataclass(frozen=True, slots=True)
class ProxmoxOptions:
    """Adapter-Optionen, aus ``AdapterConfig`` + ``extra``-Strings abgeleitet."""

    base_url: str
    timeout_seconds: float
    rate_limit_per_second: float
    max_retries: int
    retry_backoff_seconds: float
    tls_ca_bundle: str | None
    tls_verify_disabled: bool
    fetch_resource_details: bool

    @property
    def api_root(self) -> str:
        """Absoluter API-Root (mit /api2/json, genau ein Schuesselchen-Ende)."""
        root = self.base_url.rstrip("/")
        if root.endswith("/api2/json"):
            return root
        if root.endswith("/api2"):
            return root + "/json"
        return root + "/api2/json"


def build_options(config: AdapterConfig) -> ProxmoxOptions:
    """Erzeugt ``ProxmoxOptions`` aus der frozen ``AdapterConfig``.

    Fehlende/ungueltige Werte fallen auf sichere Defaults zurueck.
    """
    if not config.base_url:
        raise AdapterConfigError("Proxmox-Integration ist nicht konfiguriert: base_url fehlt")

    # 'http://' ist nur fuer isolierte Testnetze vorgesehen (Playbook) und
    # wird erlaubst, aber nicht als sicher betrachtet. TLS-Optionen
    # (tls_ca_bundle / tls_verify_disabled) sind nur fuer 'https://' relevant.
    base_url = str(config.base_url).rstrip("/")

    return ProxmoxOptions(
        base_url=base_url,
        timeout_seconds=config.timeout_seconds,
        rate_limit_per_second=_parse_float(
            config.extra.get("rate_limit_per_second"), DEFAULT_RATE_LIMIT_PER_SECOND
        ),
        max_retries=_parse_int(config.extra.get("max_retries"), DEFAULT_MAX_RETRIES),
        retry_backoff_seconds=_parse_float(
            config.extra.get("retry_backoff_seconds"), DEFAULT_RETRY_BACKOFF_SECONDS
        ),
        tls_ca_bundle=(config.extra.get("tls_ca_bundle") or None),
        tls_verify_disabled=_parse_bool(config.extra.get("tls_verify_disabled")),
        fetch_resource_details=_parse_bool(config.extra.get("fetch_resource_details"), default=True),
    )


def _parse_float(raw: str | None, default: float) -> float:
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _parse_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
