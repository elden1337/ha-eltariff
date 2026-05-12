"""ActivePowerPriceSensor entity."""

from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry

from ..const import VAT_MODE_INC
from ..coordinator import EltariffCoordinator
from .base import EltariffSensorBase


class ActivePowerPriceSensor(EltariffSensorBase):
    _attr_name = "Active power price"
    _attr_icon = "mdi:transmission-tower"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EltariffCoordinator, entry: ConfigEntry, vat_mode: str) -> None:
        super().__init__(coordinator, entry, "active_power_price")
        self._vat_mode = vat_mode

    @property
    def native_value(self) -> float | None:
        pc = self._data.snapshot.active_power_component
        if pc is None:
            return None
        return pc.price.price_inc_vat if self._vat_mode == VAT_MODE_INC else pc.price.price_ex_vat

    @property
    def native_unit_of_measurement(self) -> str | None:
        pc = self._data.snapshot.active_power_component
        return f"{pc.price.currency}/kW" if pc else None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = self._last_updated_attr()
        pc = self._data.snapshot.active_power_component
        if pc:
            attrs["reference"] = pc.reference
            attrs["currency"] = pc.price.currency
        return attrs
