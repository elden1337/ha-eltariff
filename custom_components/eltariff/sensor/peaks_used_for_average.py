"""PeaksUsedForAverageSensor entity."""
from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry

from ..coordinator import EltariffCoordinator
from .base import EltariffSensorBase


class PeaksUsedForAverageSensor(EltariffSensorBase):
    _attr_name = "Peaks used for average"
    _attr_icon = "mdi:chart-bar"
    _attr_native_unit_of_measurement = "peaks"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EltariffCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "peaks_used_for_average")

    @property
    def native_value(self) -> int | None:
        pc = self._data.snapshot.active_power_component
        if pc and pc.peak_identification_settings:
            return pc.peak_identification_settings.number_of_peaks_for_average
        return None

    @property
    def extra_state_attributes(self) -> dict:
        return self._common_attrs()
