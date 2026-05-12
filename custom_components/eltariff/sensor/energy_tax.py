"""EnergyTaxSensor entity."""
from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry

from ..const import VAT_MODE_INC
from ..coordinator import EltariffCoordinator
from .base import EltariffSensorBase


class EnergyTaxSensor(EltariffSensorBase):
    _attr_name = "Energy tax"
    _attr_icon = "mdi:percent"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EltariffCoordinator, entry: ConfigEntry, vat_mode: str) -> None:
        super().__init__(coordinator, entry, "energy_tax")
        self._vat_mode = vat_mode

    @property
    def native_value(self) -> float | None:
        comps = [c for c in self._data.snapshot.active_energy_components if c.reference == "tax"]
        if not comps:
            return None
        p = comps[0].price
        return p.price_inc_vat if self._vat_mode == VAT_MODE_INC else p.price_ex_vat

    @property
    def native_unit_of_measurement(self) -> str:
        comps = self._data.snapshot.active_energy_components
        currency = comps[0].price.currency if comps else "SEK"
        return f"{currency}/kWh"

    @property
    def extra_state_attributes(self) -> dict:
        return self._last_updated_attr()
