"""EnergyPriceTotalSensor entity."""
from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry

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

    @property
    def native_value(self) -> float:
        snap = self._data.snapshot
        if self._vat_mode == VAT_MODE_INC:
            return snap.total_energy_price_inc_vat
        return snap.total_energy_price_ex_vat

    @property
    def native_unit_of_measurement(self) -> str:
        comps = self._data.snapshot.active_energy_components
        currency = comps[0].price.currency if comps else "SEK"
        return f"{currency}/kWh"

    @property
    def extra_state_attributes(self) -> dict:
        return self._common_attrs()
