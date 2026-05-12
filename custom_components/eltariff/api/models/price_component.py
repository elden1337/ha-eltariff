"""PriceComponent dataclass."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .component_type import ComponentType
from .peak_identification_settings import PeakIdentificationSettings
from .price import Price
from .recurring_period import RecurringPeriod
from .valid_period import ValidPeriod


@dataclass
class PriceComponent:
    id: str
    reference: str
    component_type: ComponentType
    description: str
    valid_period: ValidPeriod
    price: Price
    recurring_periods: list[RecurringPeriod] = field(default_factory=list)
    peak_identification_settings: PeakIdentificationSettings | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PriceComponent:
        return cls(
            id=d["id"],
            reference=d.get("reference", ""),
            component_type=ComponentType(d["type"]),
            description=d.get("description", ""),
            valid_period=ValidPeriod.from_dict(d["validPeriod"]),
            price=Price.from_dict(d["price"]),
            recurring_periods=[RecurringPeriod.from_dict(r) for r in d.get("recurringPeriods", [])],
            peak_identification_settings=(
                PeakIdentificationSettings.from_dict(d["peakIdentificationSettings"])
                if "peakIdentificationSettings" in d
                else None
            ),
        )
