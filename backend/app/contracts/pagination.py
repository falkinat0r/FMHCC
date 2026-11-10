"""Paging-Contract (frozen).

Offset-basiert, deterministisch geordnet (siehe Endpunkt-Dokumentation).
``page_size`` max. 200.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

ItemT = TypeVar("ItemT")


class Paged(BaseModel, Generic[ItemT]):
    """Einheitliche Paging-Envelope fuer alle Listen-Endpoints."""

    items: list[ItemT]
    page: int = Field(ge=1, description="Aktuelle Seite (1-basiert)")
    page_size: int = Field(ge=1, le=200)
    total: int = Field(ge=0, description="Anzahl aller passenden Eintraege")
    total_pages: int = Field(ge=0)


def paginate(items: list[ItemT], total: int, page: int, page_size: int) -> Paged[ItemT]:
    """Erzeugt die Paged-Envelope (Routen koennen die Page-Slice selbst setzen)."""
    total_pages = (total + page_size - 1) // page_size if total else 0
    return Paged[ItemT](
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )
