"""Proxmox-Adapter (Agent 3, R1) — frozen IntegrationAdapter-Protokoll.

Verhalten:
- ``verify``        Verbindung + Token + Versionsgate (nur lesend).
- ``capabilities``  Version, Cluster-/Standalone-Modus, Quorum-Kennwert.
- ``discover``      Node → VM → LXC (nur lesend; dedup-freundliche
                    ResourceRecords mit observed_at und Parent-Referenz).
- ``health``        leichter Connection-Healthcheck (GET /version).
- ``act``           start/shutdown/reboot fuer VM und LXC (sanft,
                    async Task = UPID). Erfordert ``confirmed=True``.

Registrierung erfolgt explizit ueber ``register_proxmox_adapter()``
(nicht beim Import) — die App/Tests entscheiden den Zeitpunkt; so
bleibt die R0-Registry-Testbasis (FakeAdapter) unanfaechtig.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.adapters.base import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterState,
    AdapterStatus,
    BaseAdapter,
    ResourceRecord,
    SecretsProvider,
)
from app.adapters.errors import AdapterConfigError, AdapterError
from app.integrations import registry
from app.integrations.proxmox.actions import action_endpoint, resolve_target
from app.integrations.proxmox.client import ProxmoxClient
from app.integrations.proxmox.config import build_options, parse_token
from app.integrations.proxmox.discovery import ProxmoxDiscovery, extract_version
from app.models.integrations import AdapterKind
from app.models.mixins import utcnow

# frozen ActionJob-Model (app.models.action_jobs.ActionType)
SUPPORTED_ACTIONS = frozenset({"start", "shutdown", "reboot"})


def register_proxmox_adapter() -> None:
    """Tragt den Proxmox-Adapter in die Adapter-Registry ein (idempotent).

    Wirft NICHT, wenn ein anderer Proxmox-Adapter registriert ist
    (z. B. Test-Fixture) — die Registry-Kollision bleibt dann der
    Testlogik ueberlassen.
    """
    existing = registry.get_adapter(AdapterKind.PROXMOX)
    if existing is not None and existing is not ProxmoxAdapter:
        return
    registry.register(ProxmoxAdapter)


class ProxmoxAdapter(BaseAdapter):
    """Proxmox-VE-Adapter (Standalone + Cluster), read-first, action-ready."""

    kind = AdapterKind.PROXMOX

    # ------------------------------------------------------------- helpers

    def _build_client(self, config: AdapterConfig, secrets: SecretsProvider) -> ProxmoxClient:
        options = build_options(config)
        secret_raw = secrets.get(config.secret_ref) if config.secret_ref else None
        token = parse_token(secret_raw)
        return ProxmoxClient(options, token)

    # ------------------------------------------------------------- protocol

    async def verify(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        async with self._build_client(config, secrets) as client:
            return await ProxmoxDiscovery(client, fetch_details=False).verify()

    async def capabilities(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterCapabilities:
        async with self._build_client(config, secrets) as client:
            return await ProxmoxDiscovery(client, fetch_details=False).capabilities()

    async def discover(self, config: AdapterConfig, secrets: SecretsProvider) -> AsyncIterator[ResourceRecord]:
        options = build_options(config)
        secret_raw = secrets.get(config.secret_ref) if config.secret_ref else None
        token = parse_token(secret_raw)
        client = ProxmoxClient(options, token)
        try:
            discovery = ProxmoxDiscovery(client, fetch_details=options.fetch_resource_details)
            async for record in discovery.discover():
                yield record
        finally:
            await client.aclose()

    async def health(self, config: AdapterConfig, secrets: SecretsProvider) -> AdapterStatus:
        """Connection-Healthcheck: GET /version (Rechte nicht erforderlich).

        Netzwerk-/TLS-/Timeout-Fehler werden als AdapterError
        weitergereicht; nur ein unerwartetes 403/404 auf /version
        ergibt einen nicht-ok Status.
        """
        async with self._build_client(config, secrets) as client:
            version = await client.get_optional("/version")
            if version is None:
                return AdapterStatus(
                    state=AdapterState.API_ERROR,
                    message="Proxmox-/version-Endpunkt unerwartet nicht erreichbar",
                    checked_at=utcnow(),
                )
            return AdapterStatus(
                state=AdapterState.OK,
                api_version=extract_version(version),
                checked_at=utcnow(),
            )

    async def act(
        self,
        config: AdapterConfig,
        secrets: SecretsProvider,
        action: str,
        external_id: str,
        confirmed: bool,
    ) -> AdapterStatus:
        """Sanfte Compute-Aktion (start/shutdown/reboot), VM oder LXC.

        Die Proxmox-API antwortet asynchron mit einer UPID-Task-ID;
        ``state=ok`` bedeutet "Aktion vom Host angenommen", nicht
        "abgeschlossen" (Task-Polling siehe client-/actions-Doku).
        """
        if not confirmed:
            raise AdapterError(
                "Bestaetigung fehlt fuer Schreibaktion (confirmed=False)",
                state=AdapterState.NOT_CONFIGURED,
            )
        if action not in SUPPORTED_ACTIONS:
            raise AdapterConfigError(
                f"Aktion '{action}' wird nicht unterstuetzt (erlaubt: start, shutdown, reboot)"
            )
        resource_id = str(external_id or "").strip()
        if not resource_id.isdigit():
            raise AdapterConfigError(
                f"external_id '{external_id}' ist keine gueltige VMID/CT-ID (nur Ziffern erlaubt)"
            )

        async with self._build_client(config, secrets) as client:
            node, api = await resolve_target(client, resource_id)
            path = action_endpoint(api, action, node, resource_id)
            if path is None:  # theoretisch unerreichbar (SUPPORTED_ACTIONS-Check)
                raise AdapterConfigError(f"Aktion '{action}' nicht implementiert")
            upid = await client.post(path)

        if not isinstance(upid, str) or not upid:
            raise AdapterError(
                f"Proxmox-Antwort auf Aktion '{action}' enthaelt keine Task-UPID",
                state=AdapterState.API_ERROR,
            )
        return AdapterStatus(
            state=AdapterState.OK,
            message=f"Aktion '{action}' fuer {resource_id} angenommen (Task: {upid})",
            checked_at=utcnow(),
        )
