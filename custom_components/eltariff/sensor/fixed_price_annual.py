"""FixedPriceAnnualSensor entity."""

from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry

from ..const import VAT_MODE_INC
from ..coordinator import EltariffCoordinator
from .base import EltariffSensorBase


class FixedPriceAnnualSensor(EltariffSensorBase):
    _attr_name = "Fixed price annual"
    _attr_icon = "mdi:calendar-month"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EltariffCoordinator, entry: ConfigEntry, vat_mode: str) -> None:
        super().__init__(coordinator, entry, "fixed_price_annual")
        self._vat_mode = vat_mode

    @property
    def native_value(self) -> float | None:
        comps = self._data.snapshot.active_fixed_components
        if not comps:
            return None
        return sum(
            c.price.price_inc_vat if self._vat_mode == VAT_MODE_INC else c.price.price_ex_vat
            for c in comps
        )

    @property
    def native_unit_of_measurement(self) -> str:
        comps = self._data.snapshot.active_fixed_components
        currency = comps[0].price.currency if comps else "SEK"
        return f"{currency}/year"

    @property
    def extra_state_attributes(self) -> dict:
        comps = self._data.snapshot.active_fixed_components
        t = self._data.snapshot.tariff
        return {
            **self._last_updated_attr(),
            "valid_from": str(t.valid_period.from_including),
            "valid_to": str(t.valid_period.to_excluding),
            "components": [
                {
                    "reference": c.reference,
                    "description": c.description,
                    "price_inc_vat": c.price.price_inc_vat,
                    "price_ex_vat": c.price.price_ex_vat,
                    "currency": c.price.currency,
                    "priced_period": c.priced_period,
                }
                for c in comps
            ],
        }
