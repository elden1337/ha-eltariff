"""EnergyPriceTotalSensor entity."""

from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry

from ..api.models import PriceComponent
from ..const import VAT_MODE_INC
from ..coordinator import EltariffCoordinator
from .base import EltariffSensorBase


class EnergyPriceTotalSensor(EltariffSensorBase):
    _attr_name = "Energy price total"
    _attr_icon = "mdi:lightning-bolt"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EltariffCoordinator, entry: ConfigEntry, vat_mode: str) -> None:
        super().__init__(coordinator, entry, "energy_price_total")
        self._vat_mode = vat_mode

    def _included_components(self) -> list[tuple[str, PriceComponent]]:
        """(group, component) pairs summed into the total (energy + power-group curves)."""
        snap = self._data.snapshot
        return [("energy", c) for c in snap.active_energy_components] + [
            ("power", c) for c in snap.curve_power_components
        ]

    @property
    def native_value(self) -> float:
        # Sum at full precision, round once so curve decimals don't show in the state.
        snap = self._data.snapshot
        if self._vat_mode == VAT_MODE_INC:
            return round(snap.total_price_with_curves_inc_vat, 2)
        return round(snap.total_price_with_curves_ex_vat, 2)

    @property
    def native_unit_of_measurement(self) -> str:
        comps = self._included_components()
        currency = comps[0][1].price.currency if comps else "SEK"
        return f"{currency}/kWh"

    @property
    def extra_state_attributes(self) -> dict:
        comps = self._included_components()
        return {
            **self._last_updated_attr(),
            **self._today_schedule_attrs(),
            "components": [
                {
                    "group": group,
                    "reference": c.reference,
                    "unit": c.unit,
                    "price_inc_vat": c.price.price_inc_vat,
                    "price_ex_vat": c.price.price_ex_vat,
                    "currency": c.price.currency,
                }
                for group, c in comps
            ],
        }
