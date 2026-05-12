"""Tariff dataclass."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .price_group import PriceGroup
from .valid_period import ValidPeriod


@dataclass
class Tariff:
    id: str
    name: str
    product: str
    company_name: str
    valid_period: ValidPeriod
    fixed_price: PriceGroup | None = None
    energy_price: PriceGroup | None = None
    power_price: PriceGroup | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Tariff:
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            product=d.get("product", ""),
            company_name=d.get("companyName", ""),
            valid_period=ValidPeriod.from_dict(d["validPeriod"]),
            fixed_price=PriceGroup.from_dict(d["fixedPrice"]) if "fixedPrice" in d else None,
            energy_price=PriceGroup.from_dict(d["energyPrice"]) if "energyPrice" in d else None,
            power_price=PriceGroup.from_dict(d["powerPrice"]) if "powerPrice" in d else None,
        )
