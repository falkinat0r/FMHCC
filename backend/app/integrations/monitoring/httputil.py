"""Gemeinsame HTTP-Helfer fuer alle Adapter (Agent 4, R1).

Einheitliche Bausteine fuer die Read-only-Adapter:
- kurze Timeouts aus ``AdapterConfig.timeout_seconds``
- einheitliche Abbildung von Netzwerk-/HTTP-Fehlern auf die frozen
  AdapterError-Hierarchie (stabile AdapterState-Werte)
- Redaction von Credentials aus URLs fuer Fehlermeldungen
- optionale Transport-Injection fuer Tests (httpx.MockTransport)

Anmerkung zu Besitz: Die anderen Agent-4-Adapter (pihole, truenas, tailscale,
docker) importieren diese Helfer aus diesem Package. Falls der gemeinsame
Code weiter waechst, sollte ein gemeinsames Verzeichnis per Proposal
etabliert werden (siehe docs/agent-reports/R1-telemetry.md).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlsplit

import httpx

from app.adapters.base import AdapterConfig
from app.adapters.errors import (
    AdapterApiError,
    AdapterAuthError,
    AdapterTimeoutError,
    AdapterUnreachableError,
)

#: Credentials in der URL (http://user:pass@host) — fuer sichere Meldungen.
_CREDENTIALS_RE = re.compile(r"//[^/@]*@")


def redact_url(url: str) -> str:
    """Entfernt Credentials aus einer URL (sichere Anzeige in Meldungen)."""
    return _CREDENTIALS_RE.sub("//", url)


def safe_host(url: str) -> str:
    """Liefert nur den Netloc (ohne Credentials) einer URL fuer Meldungen."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return redact_url(url)
    return parts.netloc or redact_url(url)


def build_async_client(
    config: AdapterConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    base_url: str | None = None,
    default_headers: Mapping[str, str] | None = None,
) -> httpx.AsyncClient:
    """Erzeugt einen AsyncClient mit kurzem Timeout.

    ``base_url`` defaultiert auf ``config.base_url``. Ein Pfadpraefix der
    base_url (z. B. Reverse-Proxy) wird von httpx vor Request-Pfade gestellt
    (httpx-Verhalten: Base-Pfad wird prepended).
    """
    resolved = base_url if base_url is not None else (str(config.base_url) if config.base_url else None)
    headers = {"User-Agent": "hcc-adapter/1.0", **dict(default_headers or {})}
    return httpx.AsyncClient(
        timeout=httpx.Timeout(config.timeout_seconds, connect=config.timeout_seconds),
        headers=headers,
        follow_redirects=True,
        transport=transport,
        base_url=resolved,
    )


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    params: Mapping[str, str | int | float] | None = None,
    json_body: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
    raise_for_error: bool = True,
) -> tuple[int, object]:
    """Fuehrt eine JSON-Request aus und mapert Fehler auf AdapterError.

    Rueckgabe ``(status_code, parsed_json)``. Bei ``raise_for_error=False``
    werden 4xx/5xx nicht geworfen (fuer Versionserkennungs-Probes); das
    Payload ist dann None, wenn die Antwort kein JSON ist. Netzwerkfehler
    werden immer gemappt (Timeout/Unreachable).
    """
    try:
        response = await client.request(method, path, params=params, json=json_body, headers=headers)
    except httpx.TimeoutException as exc:
        raise AdapterTimeoutError(f"Timeout bei {path} ({type(exc).__name__})") from exc
    except httpx.ConnectError as exc:
        raise AdapterUnreachableError(f"Ziel nicht erreichbar ({path})") from exc
    except httpx.HTTPError as exc:
        raise AdapterUnreachableError(f"Netzwerkfehler bei {path} ({type(exc).__name__})") from exc

    if raise_for_error and response.status_code in (401, 403):
        raise AdapterAuthError(f"Zugriff verweigert (HTTP {response.status_code}) bei {path}")
    if raise_for_error and response.status_code >= 400:
        raise AdapterApiError(f"HTTP {response.status_code} bei {path}", http_status=response.status_code)

    payload: object
    try:
        payload = response.json() if response.content else None
    except ValueError:
        if raise_for_error and response.status_code < 400:
            raise AdapterApiError(
                f"Antwort ist kein JSON bei {path}", http_status=response.status_code
            ) from None
        payload = None
    return response.status_code, payload
