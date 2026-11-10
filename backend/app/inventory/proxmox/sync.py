"""Proxmox-Inventar-Sync (Agent 3, R1).

Duenne Schicht ueber dem frozen Inventory-Schreibweg
``app.inventory.base.upsert_resources``: nimmt die Discover-Ergebnisse
des Proxmox-Adapters entgegen und upsertet sie idempotent ins Inventar.
Synchron, da der einzige Inventar-Schreibweg (``upsert_resources``)
synchron ist — async-Orchestrierung passiert auf Service-Ebene.

- Duplikate werden ueber den Resource-Key
  ``(integration_id, resource_type, external_id)`` verhindert.
- Datenherkunft ist stets ``source=api`` (frozen ``ResourceSource``).
- ``observed_at``/``last_seen_at`` tragen die Discover-Zeit (UTC).
- Beziehungen Node→VM/LXC entstehen mit Evidenz ``api``
  (``relation_type=runs_on``), nur wenn der Parent existiert.

Dieses Modul erzeugt KEINEN zweiten Schreibweg und aendert die
frozen Contracts/Migrationen nicht — es ruft nur den einzigen
zulassigen Inventar-Schreibweg auf.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.adapters.base import ResourceRecord
from app.inventory.base import upsert_resources
from app.models.integrations import Integration


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Zusammenfassung eines Inventar-Syncs (fuer Logs/Audit/Tests)."""

    total: int
    created: int
    updated: int
    relations_created: int


def sync_proxmox_inventory(
    db: Session,
    *,
    integration: Integration,
    records: list[ResourceRecord],
) -> SyncResult:
    """Upsertet Proxmox-ResourceRecords idempotent ins Inventar.

    Der Adapter liefert ``records`` (via ``ProxmoxAdapter.discover``).
    Adapter-Fehler (unreachable/auth/…) werden hier NICHT abgefangen —
    der aufrufende Service entscheidet ueber die HTTP-/Fehler-Mapping.
    """
    result = upsert_resources(db, integration, records)
    return SyncResult(
        total=len(records),
        created=result.created,
        updated=result.updated,
        relations_created=result.relations_created,
    )
