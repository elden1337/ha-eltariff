"""Snapshot dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .price import PriceComponent
from .tariff import Tariff


@dataclass
class ActiveTariffSnapshot:
    """Result of resolving which tariff components are active at a given moment."""
    at: datetime
    tariff: Tariff
    active_power_components: list[PriceComponent]
    active_energy_components: list[PriceComponent]
    active_fixed_components: list[PriceComponent]
    parse_warnings: list[str] = field(default_factory=list)

    @property
    def active_power_component(self) -> PriceComponent | None:
        return self.active_power_components[0] if self.active_power_components else None

    @property
    def total_energy_price_inc_vat(self) -> float:
        return sum(c.price.price_inc_vat for c in self.active_energy_components)

    @property
    def total_energy_price_ex_vat(self) -> float:
        return sum(c.price.price_ex_vat for c in self.active_energy_components)


@dataclass
class ScheduleSlot:
    """One contiguous time band in a day schedule."""
    start: datetime
    end: datetime
    band_reference: str
    price_inc_vat: float
    price_ex_vat: float
    currency: str
