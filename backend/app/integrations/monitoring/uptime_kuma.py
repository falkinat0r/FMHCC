"""Read-only-Adapter für vorhandene Uptime Kuma-Instanzen (Agent 4, R1).

Grenzen (bewusst eng, klar dokumentiert):
- Verbindung (``GET /api/status``), optionales Session-Login
  (``POST /api/login``, User+Passwort über secret_ref als ``user:pass``),
  Monitor-Liste (``GET /api/monitor``) als Discover + Service-Verfügbarkeit.
- Keine Heartbeat-Feinanalyse, keine Schreibanfänge.

Authentifizierung: Uptime Kuma v1 verwendet Session-Auth (Passport) —
keine API-Token. Ohne Credentials bleibt nur der öffentliche Status-Check.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx

from app.adapters.base import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterState,
    AdapterStatus,
    ResourceRecord,
    SecretsProvider,
)
from app.adapters.errors import AdapterApiError, AdapterAuthError, AdapterConfigError
from app.integrations.monitoring.base import BaseMonitoringBackend, ServiceAvailability
from app.integrations.monitoring.httputil import build_async_client, request_json
from app.models.integrations import AdapterKind
from app.models.resources import ResourceStatus, ResourceType

__all__ = ["UptimeKumaBackend"]

_STATUS_MAP: dict[str, ResourceStatus] = {
    "up": ResourceStatus.HEALTHY,
    "down": ResourceStatus.DOWN,
    "paused": ResourceStatus.UNKNOWN,
}


class UptimeKumaBackend(BaseMonitoringBackend):
    """Uptime Kuma HTTP-API als Uptime-Quelle (read-only)."""

    name = "uptime_kuma"
    kind = AdapterKind.MONITORING

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @staticmethod
    def _require_base_url(config: AdapterConfig) -> None:
        if not config.base_url:
            raise AdapterConfigError("Uptime Kuma: base_url nicht konfiguriert")

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        """Status-Check (öffentlich); mit Credentials zusätzlich Login-Test."""
        self._require_base_url(config)
        async with build_async_client(config, transport=self._transport) as client:
            status_code, payload = await request_json(client, "GET", "/api/status", raise_for_error=False)
        if status_code != 200:
            if status_code in (401, 403):
                raise AdapterAuthError(f"Zugriff verweigert (HTTP {status_code}) bei /api/status")
            raise AdapterApiError(
                f"Uptime Kuma /api/status antwortet mit HTTP {status_code}", http_status=status_code
            )
        body = payload if isinstance(payload, dict) else {}
        if body.get("status") != "UP":
            return AdapterStatus(
                state=AdapterState.API_ERROR,
                message=f"Uptime Kuma-Status '{body.get('status')}'",
                checked_at=datetime.now(UTC),
            )
        if config.secret_ref:
            user, password = self._credentials(config, secrets)
            async with build_async_client(config, transport=self._transport) as client:
                await self._perform_login(client, user, password)
        return AdapterStatus(
            state=AdapterState.OK,
            message="Uptime Kuma erreichbar",
            api_version=None,
            checked_at=datetime.now(UTC),
        )

    @staticmethod
    def _credentials(config: AdapterConfig, secrets: SecretsProvider) -> tuple[str, str]:
        """Credentials 'user:pass' auflösen (fehlend => AdapterError)."""
        if not config.secret_ref:
            raise AdapterAuthError("Credentials nicht konfiguriert (secret_ref 'user:pass' erforderlich)")
        credentials = secrets.get(config.secret_ref)
        if credentials is None:
            raise AdapterAuthError("Credentials nicht gesetzt (Secret-Referenz ohne Wert)")
        user, _, password = credentials.partition(":")
        if not user or not password:
            raise AdapterAuthError("Credentials-Maske 'user:pass' unvollständig")
        return user, password

    @staticmethod
    async def _perform_login(client: httpx.AsyncClient, user: str, password: str) -> None:
        """Session-Login auf einem geöffneten Client (Cookie-Jar wird gesetzt)."""
        status_code, payload = await request_json(
            client,
            "POST",
            "/api/login",
            json_body={"username": user, "password": password, "remember": True},
            raise_for_error=False,
        )
        if status_code in (401, 403):
            raise AdapterAuthError("Uptime Kuma-Login fehlgeschlagen (ungültige Zugangsdaten)")
        if status_code != 200:
            raise AdapterApiError(f"Uptime Kuma-Login HTTP {status_code}", http_status=status_code)
        message = str(payload.get("message", "")) if isinstance(payload, dict) else ""
        if "error" in message.lower() or "invalid" in message.lower():
            raise AdapterAuthError("Uptime Kuma-Login fehlgeschlagen")

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        status = await self.verify(config, secrets)
        features = ["verify", "health", "source_status"]
        if config.secret_ref:
            features += ["discover", "availability"]
        return AdapterCapabilities(
            features=features,
            api_version=status.api_version,
            extra={"backend": "uptime_kuma"},
        )

    async def _monitors(self, config: AdapterConfig, secrets: SecretsProvider) -> list[dict]:
        user, password = self._credentials(config, secrets)
        async with build_async_client(config, transport=self._transport) as client:
            await self._perform_login(client, user, password)
            _, payload = await request_json(client, "GET", "/api/monitor")
        return payload if isinstance(payload, list) else []

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        """Monitore als OTHER-Ressourcen (Service-Monitore von Uptime Kuma)."""
        self._require_base_url(config)
        now = datetime.now(UTC)
        for monitor in await self._monitors(config, secrets):
            if not isinstance(monitor, dict) or monitor.get("id") is None:
                continue
            monitor_id = monitor["id"]
            host = str(monitor.get("host") or "")
            port = monitor.get("port")
            external = f"{host}:{port}" if host and port is not None else str(monitor.get("name") or monitor_id)
            yield ResourceRecord(
                resource_type=ResourceType.OTHER,
                external_id=f"monitor-{monitor_id}",
                name=str(monitor.get("name") or external),
                status=_STATUS_MAP.get(str(monitor.get("status", "")), ResourceStatus.UNKNOWN),
                payload={
                    "origin": "uptime_kuma monitor",
                    "type": str(monitor.get("type") or "unknown"),
                    "host": host or None,
                    "port": port,
                    "status": str(monitor.get("status") or "unknown"),
                },
                observed_at=now,
            )

    async def service_availability(
        self, config: AdapterConfig, secrets: SecretsProvider
    ) -> list[ServiceAvailability]:
        self._require_base_url(config)
        now = datetime.now(UTC)
        out: list[ServiceAvailability] = []
        for monitor in await self._monitors(config, secrets):
            if not isinstance(monitor, dict):
                continue
            name = str(monitor.get("name") or monitor.get("id"))
            status = _STATUS_MAP.get(str(monitor.get("status", "")), ResourceStatus.UNKNOWN)
            out.append(
                ServiceAvailability(
                    service=name,
                    status=status,
                    checked_at=now,
                    detail=str(monitor.get("status") or "unknown"),
                )
            )
        return out
