"""Tariff dataclasses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .price import PriceGroup
from .schedule import CalendarPattern, ValidPeriod


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


@dataclass
class TariffCollection:
    tariffs: list[Tariff]
    calendar_patterns: list[CalendarPattern]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TariffCollection:
        return cls(
            tariffs=[Tariff.from_dict(t) for t in d.get("tariffs", [])],
            calendar_patterns=[CalendarPattern.from_dict(p) for p in d.get("calendarPatterns", [])],
        )

    def get_tariff(self, tariff_id: str) -> Tariff | None:
        return next((t for t in self.tariffs if t.id == tariff_id), None)

    def get_calendar_pattern(self, pattern_id: str) -> CalendarPattern | None:
        return next((p for p in self.calendar_patterns if p.id == pattern_id), None)
