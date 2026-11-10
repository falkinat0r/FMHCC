"""Tailscale-Integration (Agent 4, R1).

Read-only-Adapter mit zwei Zugriffsmodellen: Tailnet-Management-API
('api') und lokale Client-Info über die Local API des tailscaled
('local').
"""

from app.integrations.tailscale.adapter import TailscaleAdapter, TailscaleMode

__all__ = ["TailscaleAdapter", "TailscaleMode"]
