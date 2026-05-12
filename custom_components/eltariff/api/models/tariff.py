"""Tariff dataclass."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    description: str | None = None
    time_zone: str | None = None
    last_updated: datetime | None = None
    company_org_no: str | None = None
    direction: str | None = None
    # ISO 8601 duration string (e.g. "PT15M", "PT1H", "P1M")
    billing_period: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Tariff:
        raw_last_updated = d.get("lastUpdated")
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            product=d.get("product", ""),
            company_name=d.get("companyName", ""),
            valid_period=ValidPeriod.from_dict(d["validPeriod"]),
            fixed_price=PriceGroup.from_dict(d["fixedPrice"]) if "fixedPrice" in d else None,
            energy_price=PriceGroup.from_dict(d["energyPrice"]) if "energyPrice" in d else None,
            power_price=PriceGroup.from_dict(d["powerPrice"]) if "powerPrice" in d else None,
            description=d.get("description"),
            time_zone=d.get("timeZone"),
            last_updated=datetime.fromisoformat(raw_last_updated) if raw_last_updated else None,
            company_org_no=d.get("companyOrgNo"),
            direction=d.get("direction"),
            billing_period=d.get("billingPeriod"),
        )
