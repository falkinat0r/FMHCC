"""Proxmox-API-Client (Agent 3, R1).

Eigenschaften:
- API-Token-Authentifizierung via ``Authorization: PVEAPIToken=<id>=<secret>``
  (keine Passwort-/Ticket-Auth, keine Root-Passwoerter).
- Sichere TLS-Verifizierung als Standard. Vertrauensstellung ist
  konfigurierbar (``tls_ca_bundle``); eine Abschaltung ist nur ein
  explizites, WARNING-geLoggtes Opt-in (``tls_verify_disabled``) —
  niemals Default.
- Zeitueberschreitung ueber httpx-Timeouts (Konfig: AdapterConfig).
- Fehlerbehandlung: stabile Mauerung auf die AdapterError-Hierarchie
  (unreachable/timeout/auth_failed/api_error); Message ohne Secrets.
- Retry NUR fuer idempotente GET-Anfragen (Transportfehler, 502/503/504)
  mit exponentiellem Backoff. Schreibaktionen (POST) werden nie wiederholt.
- Rate-Limiting: minimale Abstandsregel pro Client-Instanz
  (Begrenzung der Abfragehaeufigkeit).
- Connection-Healthcheck: leichtgewichtiger GET /version ohne Auth-Zwang.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from collections.abc import Mapping
from typing import Any

import httpx

from app.adapters.errors import (
    AdapterApiError,
    AdapterAuthError,
    AdapterError,
    AdapterTimeoutError,
    AdapterUnreachableError,
)
from app.integrations.proxmox.config import ProxmoxOptions, ProxmoxToken

logger = logging.getLogger("hcc.adapter.proxmox")

# HTTP-Status, die bei idempotenten GETs erneut versuchs werden
_RETRYABLE_STATUSES = frozenset({502, 503, 504})

# NUR fuer Tests: globaler Transport-Ueberschreiber (z. B. httpx.MockTransport).
# In Produktion bleibt er None — dann wird das normale Netzwerk verwendet.
_TEST_TRANSPORT: httpx.AsyncBaseTransport | None = None


def set_test_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Testhelfer: routet alle Client-Anfragen ueber ``transport`` (kein Netzwerk)."""
    global _TEST_TRANSPORT
    _TEST_TRANSPORT = transport


class _RateLimiter:
    """Asynchroner Mindest-Abstands-Limiter (Begrenzung der Abfragehaeufigkeit).

    Simplesemantik: zwischen zwei Request-Versuchen pro Instanz vergehen
    mindestens 1/rate Sekunden. Genuegend konservative Schutzmassnahme
    gegen Proxmox-Instanzen; pro Adapter-Instanz (und damit pro
    Integration) wirkt, ohne Shared-State.
    """

    def __init__(self, rate_per_second: float) -> None:
        self._min_interval = 1.0 / rate_per_second if rate_per_second > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                self._next_allowed += self._min_interval
                await asyncio.sleep(wait)
            else:
                self._next_allowed = now + self._min_interval


class ProxmoxClient:
    """Async-HTTP-Client fuer die Proxmox api2/json-Schnittstelle.

    Nutzung::

        async with ProxmoxClient(options, token) as client:
            nodes = await client.get("/nodes")
            assert isinstance(nodes, list)

    Alle Methoden werfen ``AdapterError``-Abkoemmlinge bei Fehlern —
    nie rohe httpx-Exceptions.
    """

    def __init__(
        self,
        options: ProxmoxOptions,
        token: ProxmoxToken,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._options = options
        effective_transport = transport if transport is not None else _TEST_TRANSPORT

        if options.tls_verify_disabled:
            verify: bool | str = False
            logger.warning(
                "Proxmox-Adapter: TLS-Zertifikatspruefung ist AEGEALTET (explizites Opt-in) fuer %s",
                options.base_url,
            )
        elif options.tls_ca_bundle:
            verify = options.tls_ca_bundle
        else:
            verify = True

        self._http = httpx.AsyncClient(
            verify=verify,
            timeout=httpx.Timeout(options.timeout_seconds),
            transport=effective_transport,
            headers={
                "Authorization": f"PVEAPIToken={token.token_id}={token.secret}",
                "Content-Type": "application/json",
            },
        )
        self._limiter = _RateLimiter(options.rate_limit_per_second)

    # ------------------------------------------------------------------ lifecycle

    async def __aenter__(self) -> ProxmoxClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ API

    async def get(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        """Idempotente GET-Anfrage (mit Retry). Liefert den 'data'-Wert."""
        return await self._request("GET", path, params=params, retryable=True)

    async def get_optional(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        """GET, dessen Fehlschlag erlaubt ist (Rechte/Ressource fehlen).

        403 (unzureichende Berechtigung) und 404 (Ressource fehlt) liefern
        ``None`` statt einer Exception. 401, 5xx, Netzwerk- und
        Timeout-Fehler werden weitergeleitet (das sind keine
        "Option-Fehler").
        """
        try:
            return await self.get(path, params=params)
        except AdapterAuthError as exc:
            if exc.details.get("http_status") == 403:
                return None
            raise
        except AdapterApiError as exc:
            if exc.http_status == 404:
                return None
            raise

    async def post(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        """Schreibaktion (POST). WIRD NIE WIEDERHOLT (kein Retry)."""
        return await self._request("POST", path, params=params, retryable=False)

    async def get_tolerant(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        """GET fuer optionale Ergaenzungsdaten: jeder AdapterError → ``None``.

        Fuer Details, deren Fehlen die Discovery nicht abbrechen soll
        (Node-Status/Storage/Tasks, VM-/LXC-Config, Snapshots,
        Cluster-Health): 403 (Rechte), 404 (Ressource), 5xx (Node
        antwortet nicht korrekt) und Timeout degradieren auf None.
        """
        try:
            return await self.get(path, params=params)
        except AdapterError:
            return None

    # ------------------------------------------------------------------ internals

    async def _request(self, method: str, path: str, *, params, retryable: bool) -> Any:
        url = self._options.api_root + path
        attempts = (self._options.max_retries + 1) if retryable else 1
        backoff = self._options.retry_backoff_seconds
        last_status: int | None = None

        for attempt in range(attempts):
            await self._limiter.acquire()
            try:
                response = await self._http.request(method, url, params=params)
            except httpx.TimeoutException as exc:
                raise AdapterTimeoutError(
                    f"Proxmox-API-Antwort ist zu langsam (Timeout) fuer {path}",
                    details={"path": path, "timeout_seconds": self._options.timeout_seconds},
                ) from exc
            except httpx.HTTPError as exc:  # ConnectError, ReadError, TLS, ...
                raise self._classify_transport_error(exc, path) from exc

            last_status = response.status_code
            if (
                retryable
                and attempt < attempts - 1
                and (last_status in _RETRYABLE_STATUSES or last_status >= 500)
            ):
                await asyncio.sleep(backoff * (2**attempt))
                continue
            return self._decode(last_status, response, path)

        # Alle Versuche mit serverseitigem 5xx beantwortet
        raise AdapterApiError(
            f"Proxmox-API-Fehler (HTTP {last_status}) auf {path} nach {attempts} Versuchen",
            http_status=last_status,
            details={"path": path},
        )

    def _classify_transport_error(self, exc: httpx.HTTPError, path: str) -> AdapterError:
        """Mauert Transportfehler (DNS, Refused, TLS) auf stabile AdapterStates."""
        cause: BaseException | None = exc
        seen: set[int] = set()
        while cause is not None and id(cause) not in seen:
            seen.add(id(cause))
            if isinstance(cause, ssl.SSLError):
                return AdapterUnreachableError(
                    "TLS-Verbindung fehlgeschlagen (Zertifikat nicht vertrauenswuerdig oder abgelaufen)",
                    details={"path": path, "tls": True, "reason": str(cause)[:200]},
                )
            cause = cause.__cause__ or cause.__context__
        return AdapterUnreachableError(
            f"Proxmox-API nicht erreichbar (Verbindungsfehler bei {path})",
            details={"path": path, "tls": False},
        )

    def _decode(self, status: int, response: httpx.Response, path: str) -> Any:
        """Prueft den Status und loest die Proxmox-Envelope ('data')."""
        if status == 401:
            raise AdapterAuthError(
                "Proxmox-API-Token ist ungültig, abgelaufen oder widerrufen (HTTP 401)",
                details={"path": path, "http_status": 401},
            )
        if status == 403:
            raise AdapterAuthError(
                "Proxmox-API-Token hat unzureichende Berechtigungen (HTTP 403)",
                details={"path": path, "http_status": 403},
            )
        if status >= 400:
            raise AdapterApiError(
                f"Proxmox-API-Fehler (HTTP {status}) auf {path}",
                http_status=status,
                details=self._error_details(response, path),
            )

        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise AdapterApiError(
                f"Fehlerhafte API-Antwort (kein JSON) auf {path}",
                http_status=status,
                details={"path": path},
            ) from exc
        if not isinstance(body, dict) or "data" not in body:
            raise AdapterApiError(
                f"Fehlerhafte API-Antwort (fehlendes 'data'-Feld) auf {path}",
                http_status=status,
                details={"path": path},
            )
        return body.get("data")

    @staticmethod
    def _error_details(response: httpx.Response, path: str) -> dict[str, Any]:
        """Fehlerdetails aus der Proxmox-Fehler-Envelope (ohne Secrets)."""
        details: dict[str, Any] = {"path": path, "http_status": response.status_code}
        try:
            body = response.json()
        except ValueError:
            return details
        if isinstance(body, dict):
            messages = body.get("messages") or body.get("errors")
            if messages:
                items = messages if isinstance(messages, list) else [messages]
                details["api_messages"] = [str(item)[:200] for item in items[:5]]
        return details
