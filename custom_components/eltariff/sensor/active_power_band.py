"""ActivePowerBandSensor entity."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from ..coordinator import EltariffCoordinator
from .base import EltariffSensorBase


class ActivePowerBandSensor(EltariffSensorBase):
    _attr_name = "Active power band"
    _attr_icon = "mdi:clock-time-four-outline"

    def __init__(self, coordinator: EltariffCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "active_power_band")

    @property
    def native_value(self) -> str | None:
        pc = self._data.snapshot.active_power_component
        return pc.reference if pc else None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = self._common_attrs()
        attrs["parse_warnings"] = self._data.snapshot.parse_warnings
        return attrs
