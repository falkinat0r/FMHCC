"""Adapter-Registry (Foundation, frozen).

Konkrete Adapter werden von den Folge-Agenten in ihre Verzeichnisse
(``app/integrations/<kind>/``) gelegt und per ``@register`` hier eingetragen.
In R0 ist die Registry bewusst leer — Endpunkte antworten dann ehrlich mit
``not_implemented``, statt zu stubben.
"""

from __future__ import annotations

from app.adapters.base import IntegrationAdapter
from app.models.integrations import AdapterKind

_REGISTRY: dict[str, type[IntegrationAdapter]] = {}


def register(cls: type[IntegrationAdapter]) -> type[IntegrationAdapter]:
    """Decorator: Adapter-Klasse in die Registry eintragen."""
    key = cls.kind.value
    if key in _REGISTRY and _REGISTRY[key] is not cls:
        raise ValueError(f"Adapter '{key}' ist bereits registriert")
    _REGISTRY[key] = cls
    return cls


def get_adapter(kind: AdapterKind | str) -> type[IntegrationAdapter] | None:
    key = kind.value if isinstance(kind, AdapterKind) else str(kind)
    return _REGISTRY.get(key)


def available_adapters() -> list[str]:
    return sorted(_REGISTRY.keys())


def _reset_for_tests() -> None:
    """Nur fuer Tests."""
    _REGISTRY.clear()
