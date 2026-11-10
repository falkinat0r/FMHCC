"""Pi-hole-Integration: Adapter für (mehrere) Pi-hole-Instanzen (Agent 4, R1).

Unterstützte API-Generationen (quellenbasiert verifiziert, siehe
docs/agent-reports/R1-telemetry.md):

- **v6 (REST, FTL ≥ 6.0):** ``/api/*``, OpenAPI-Specs; Auth: Session via
  ``POST /api/auth`` (Passwort), SID über Header ``X-FTL-SID``.
  Erkennung: ``GET /api/info/login`` (auth-frei) liefert ``{https_port, dns}``.
- **v5 (Legacy, Core 5.x / Web 5.x):** ``GET /admin/api.php?summaryRaw``;
  Auth: ``?auth=<pwhash>`` (WEBPASSWORD aus setupVars.conf,
  d. h. sha256(sha256(password))). Erkennung: ``GET /admin/api.php?versions``
  (auth-frei) liefert ``{core_current, web_current, FTL_current}``.

Wichtig: Pi-hole v5 hat **keine** GraphQL-/REST-API (vermutete
GraphQL-Integration entfällt); die Legacy-Face ist ``api.php``.

Mehrere Instanzen = mehrere Integrationen (je eine mit eigenem
``integration_id``, ``base_url`` und ``secret_ref``). Read-only: es werden
nur lesende Requests ausgesendet.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx

from app.adapters.base import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterState,
    AdapterStatus,
    BaseAdapter,
    MetricsRecord,
    MetricValue,
    ResourceRecord,
    SecretsProvider,
)
from app.adapters.errors import (
    AdapterApiError,
    AdapterAuthError,
    AdapterConfigError,
    AdapterVersionError,
)
from app.integrations.monitoring.httputil import build_async_client, request_json
from app.integrations.registry import register
from app.models.integrations import AdapterKind
from app.models.resources import ResourceStatus, ResourceType

__all__ = ["PiholeApiGeneration", "PiholeAdapter"]


class PiholeApiGeneration(StrEnum):
    """Erkannte Pi-hole-API-Generation."""

    V6 = "v6"  # REST-API /api (FTL >= 6.0)
    V5 = "v5"  # Legacy api.php (Core 5.x / Web 5.x)


@register
class PiholeAdapter(BaseAdapter):
    """Read-only-Adapter für Pi-hole (v5 api.php und v6 REST)."""

    kind = AdapterKind.PIHOLE

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._v6_sid: str | None = None

    @staticmethod
    def _require_base_url(config: AdapterConfig) -> None:
        if not config.base_url:
            raise AdapterConfigError("Pi-hole: base_url nicht konfiguriert")

    # -- API-Erkennung (auth-frei) ---------------------------------------

    async def _detect(self, config: AdapterConfig) -> tuple[PiholeApiGeneration, str | None]:
        """Erkennt die API-Generation ohne Credentials."""
        self._require_base_url(config)
        async with build_async_client(config, transport=self._transport) as client:
            status, _ = await request_json(client, "GET", "/api/info/login", raise_for_error=False)
        if status == 200:
            return PiholeApiGeneration.V6, None
        async with build_async_client(config, transport=self._transport) as client:
            status, payload = await request_json(
                client, "GET", "/admin/api.php", params={"versions": ""}, raise_for_error=False
            )
        if status == 200 and isinstance(payload, dict) and payload.get("FTL_current"):
            return PiholeApiGeneration.V5, str(payload["FTL_current"])
        raise AdapterVersionError(
            "Pi-hole-API nicht erkannt (erwartet: v6 REST /api oder v5 /admin/api.php)"
        )

    # -- Auth -------------------------------------------------------------

    async def _v6_auth(self, config: AdapterConfig, secrets: SecretsProvider) -> str | None:
        """Session (SID) für v6; None, wenn die Instanz ohne Auth läuft."""
        if not config.secret_ref:
            # Auth-freie Instanz prüfen (GET /api/auth liefert valid/sid-Info)
            async with build_async_client(config, transport=self._transport) as client:
                status, payload = await request_json(client, "GET", "/api/auth", raise_for_error=False)
            body = payload if isinstance(payload, dict) else {}
            if status == 200 and body.get("valid") is True and body.get("sid") is None:
                return None
            raise AdapterAuthError("Pi-hole v6 benötigt ein Passwort, aber es ist kein Secret konfiguriert")
        password = secrets.get(config.secret_ref)
        if password is None:
            raise AdapterAuthError("Passwort nicht gesetzt (Secret-Referenz ohne Wert)")
        async with build_async_client(config, transport=self._transport) as client:
            status, payload = await request_json(
                client, "POST", "/api/auth", json_body={"password": password}, raise_for_error=False
            )
        if status in (401, 403):
            raise AdapterAuthError("Pi-hole v6: Login fehlgeschlagen (ungültiges Passwort)")
        if status != 200:
            raise AdapterApiError(f"Pi-hole v6: Login antwortet mit HTTP {status}", http_status=status)
        session = payload.get("session") if isinstance(payload, dict) else None
        sid = session.get("sid") if isinstance(session, dict) else None
        if not sid:
            raise AdapterApiError("Pi-hole v6: Login-Antwort ohne Session (SID fehlt)")
        return str(sid)

    def _v5_auth(self, config: AdapterConfig, secrets: SecretsProvider) -> str | None:
        """pwhash für v5 (WEBPASSWORD aus setupVars.conf); None ohne Secret."""
        if not config.secret_ref:
            return None
        pwhash = secrets.get(config.secret_ref)
        if pwhash is None:
            raise AdapterAuthError("Pi-hole v5: pwhash nicht gesetzt (Secret-Referenz ohne Wert)")
        return pwhash

    # -- IntegrationAdapter-Protokoll -------------------------------------

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        """Verbindung + API-Generation + Auth prüfen (nur lesende Requests)."""
        generation, api_version = await self._detect(config)
        if generation is PiholeApiGeneration.V6:
            self._v6_sid = await self._v6_auth(config, secrets)
        else:
            await self._verify_v5(config, secrets)
        return AdapterStatus(
            state=AdapterState.OK,
            message=f"Pi-hole erreichbar (API {generation.value})",
            api_version=api_version or f"{generation.value} (Version nicht abgefragt)",
            checked_at=datetime.now(UTC),
        )

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        generation, api_version = await self._detect(config)
        return AdapterCapabilities(
            features=["verify", "health", "source_status", "discover", "metrics"],
            api_version=api_version or f"{generation.value}",
            extra={"api": generation.value},
        )

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        """Die Pi-hole-Instanz selbst als DNS_STATS-Ressource."""
        generation, api_version = await self._detect(config)
        yield ResourceRecord(
            resource_type=ResourceType.DNS_STATS,
            external_id="summary",
            name=f"Pi-hole ({generation.value})",
            status=ResourceStatus.HEALTHY,
            payload={"origin": "pihole", "api": generation.value, "api_version": api_version},
            observed_at=datetime.now(UTC),
        )

    async def collect(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        resource_type: ResourceType,
        external_id: str,
    ) -> MetricsRecord:
        """Aktuelle DNS-Statistiken (queries/blocked/Percent/Blocking-Status)."""
        if resource_type is not ResourceType.DNS_STATS or external_id != "summary":
            raise AdapterConfigError(
                f"Pi-hole: unerwartete Ressource '{resource_type.value}/{external_id}' (erwartet: dns_stats/summary)"
            )
        generation, _ = await self._detect(config)
        if generation is PiholeApiGeneration.V6:
            metrics = await self._collect_v6(config, secrets)
        else:
            metrics = await self._collect_v5(config, secrets)
        return MetricsRecord(
            external_id=external_id,
            resource_type=resource_type,
            metrics=metrics,
            collected_at=datetime.now(UTC),
        )

    # -- v6 REST -----------------------------------------------------------

    async def _collect_v6(self, config: AdapterConfig, secrets: SecretsProvider) -> dict[str, MetricValue]:
        sid = await self._v6_auth(config, secrets)
        metrics: dict[str, MetricValue] = {}
        async with build_async_client(
            config,
            transport=self._transport,
            default_headers={"X-FTL-SID": sid} if sid else {},
        ) as client:
            _, blocking_payload = await request_json(client, "GET", "/api/dns/blocking")
            _, summary_payload = await request_json(client, "GET", "/api/stats/summary")

        blocking_raw = blocking_payload.get("blocking") if isinstance(blocking_payload, dict) else None
        if blocking_raw == "enabled":
            metrics["blocking_enabled"] = MetricValue(value=1.0, unit="bool")
        elif blocking_raw == "disabled":
            metrics["blocking_enabled"] = MetricValue(value=0.0, unit="bool")
        # 'failed'/'unknown': Metrik weggelassen (keine erfundenen Werte)

        queries = summary_payload.get("queries") if isinstance(summary_payload, dict) else None
        queries = queries if isinstance(queries, dict) else {}
        if total := _as_float(queries.get("total")):
            metrics["dns_queries"] = MetricValue(value=total, unit="count")
        if blocked := _as_float(queries.get("blocked")):
            metrics["dns_blocked"] = MetricValue(value=blocked, unit="count")
        if percent := _as_float(queries.get("percent_blocked")):
            metrics["blocked_percent"] = MetricValue(value=percent, unit="percent")
        gravity = summary_payload.get("gravity") if isinstance(summary_payload, dict) else None
        gravity = gravity if isinstance(gravity, dict) else {}
        if blocked_domains := _as_float(gravity.get("domains_being_blocked")):
            metrics["blocked_domains"] = MetricValue(value=blocked_domains, unit="count")
        return metrics

    # -- v5 api.php ---------------------------------------------------------

    async def _verify_v5(self, config: AdapterConfig, secrets: SecretsProvider) -> None:
        """Lesender Probe: Auth-Status + FTL-Laufzustand prüfen."""
        pwhash = self._v5_auth(config, secrets)
        params: dict[str, str] = {"summaryRaw": ""}
        if pwhash is not None:
            params["auth"] = pwhash
        async with build_async_client(config, transport=self._transport) as client:
            _, payload = await request_json(client, "GET", "/admin/api.php", params=params)
        body = payload if isinstance(payload, dict) else {}
        if body.get("FTLnotrunning"):
            raise AdapterApiError("Pi-hole v5: FTL läuft nicht")
        if body.get("auth") is False:
            raise AdapterAuthError("Pi-hole v5: Passwort gesetzt, aber kein (gültiger) pwhash konfiguriert")

    async def _collect_v5(self, config: AdapterConfig, secrets: SecretsProvider) -> dict[str, MetricValue]:
        pwhash = self._v5_auth(config, secrets)
        metrics: dict[str, MetricValue] = {}
        async with build_async_client(config, transport=self._transport) as client:
            params: dict[str, str] = {"summaryRaw": ""}
            if pwhash is not None:
                params["auth"] = pwhash
            _, payload = await request_json(client, "GET", "/admin/api.php", params=params)

        body = payload if isinstance(payload, dict) else {}
        if body.get("FTLnotrunning"):
            raise AdapterApiError("Pi-hole v5: FTL läuft nicht", details={"raw": "FTLnotrunning"})
        if body.get("auth") is False:
            raise AdapterAuthError("Pi-hole v5: Authentifizierung erforderlich (pwhash fehlt/ungültig)")
        if status := _as_float_or_str(body.get("status")):
            if status == "enabled":
                metrics["blocking_enabled"] = MetricValue(value=1.0, unit="bool")
            elif status == "disabled":
                metrics["blocking_enabled"] = MetricValue(value=0.0, unit="bool")
        if value := _as_float(body.get("dns_queries_today")):
            metrics["dns_queries"] = MetricValue(value=value, unit="count")
        if value := _as_float(body.get("ads_blocked_today")):
            metrics["dns_blocked"] = MetricValue(value=value, unit="count")
        if value := _as_float(body.get("ads_percentage_today")):
            metrics["blocked_percent"] = MetricValue(value=value, unit="percent")
        if value := _as_float(body.get("domains_being_blocked")):
            metrics["blocked_domains"] = MetricValue(value=value, unit="count")
        return metrics


def _as_float(value: Any) -> float | None:
    """Zahlen (auch '123'-Strings) nach float; None/leer -> None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_float_or_str(value: Any) -> str | None:
    return str(value) if isinstance(value, str) else None
