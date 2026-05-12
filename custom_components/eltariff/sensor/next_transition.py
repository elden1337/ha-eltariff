"""NextTransitionSensor entity."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry

from ..coordinator import EltariffCoordinator
from .base import EltariffSensorBase


class NextTransitionSensor(EltariffSensorBase):
    _attr_name = "Next tariff transition"
    _attr_icon = "mdi:clock-fast"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: EltariffCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_transition")

    @property
    def native_value(self) -> datetime | None:
        return self._data.next_transition

    @property
    def extra_state_attributes(self) -> dict:
        return {**self._tariff_meta_attrs(), **self._today_schedule_attrs()}
