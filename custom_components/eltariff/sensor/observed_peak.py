"""ObservedPeakSensor — the minimum peak power (kW) already committed to this billing period."""

from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass

from .cost_sensor_base import CostSensorBase


class ObservedPeakSensor(CostSensorBase):
    _attr_name = "Observed peak"
    _attr_icon = "mdi:eye-arrow-right"
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, cost_service, vat_mode):
        super().__init__(coordinator, entry, cost_service, "observed_peak")

    @property
    def native_value(self) -> float | None:
        bd = self._get_breakdown()
        if bd is not None:
            return round(bd.observed_peak_kw, 3)
        return self._restored_native_value
