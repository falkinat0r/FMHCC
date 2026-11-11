"""Proxmox-Inventar-Integration (Agent 3, R1)."""

from app.inventory.proxmox.sync import SyncResult, sync_proxmox_inventory

__all__ = ["SyncResult", "sync_proxmox_inventory"]
