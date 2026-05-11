"""Price-related dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .schedule import PeakIdentificationSettings, RecurringPeriod, ValidPeriod


class ComponentType(StrEnum):
    FIXED = "fixed"
    PEAK = "peak"
    ENERGY = "energy"


@dataclass
class Price:
    price_ex_vat: float
    price_inc_vat: float
    currency: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Price:
        return cls(
            price_ex_vat=float(d["priceExVat"]),
            price_inc_vat=float(d["priceIncVat"]),
            currency=d["currency"],
        )


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


@dataclass
class PriceGroup:
    components: list[PriceComponent]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PriceGroup:
        return cls(
            components=[PriceComponent.from_dict(c) for c in d.get("components", [])]
        )
