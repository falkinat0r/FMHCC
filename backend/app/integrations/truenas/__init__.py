"""TrueNAS-Integration (Agent 4, R1).

Read-only-Adapter fuer die REST-API v2.0 (SCALE 24.04–25.10); ab 26.0
ist die REST-API entfernt (dann Version-unsupported).
"""

from app.integrations.truenas.adapter import TruenasAdapter

__all__ = ["TruenasAdapter"]
