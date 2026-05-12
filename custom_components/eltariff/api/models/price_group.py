"""PriceGroup dataclass."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .price_component import PriceComponent


@dataclass
class PriceGroup:
    components: list[PriceComponent]
    id: str | None = None
    name: str | None = None
    description: str | None = None
    cost_function: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PriceGroup:
        return cls(
            components=[PriceComponent.from_dict(c) for c in d.get("components", [])],
            id=d.get("id"),
            name=d.get("name"),
            description=d.get("description"),
            cost_function=d.get("costFunction"),
        )
