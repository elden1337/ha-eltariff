"""ChargedPeakSensor — the peak power (kW) currently charged for this billing period."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorStateClass

from .cost_sensor_base import CostSensorBase


class ChargedPeakSensor(CostSensorBase):
    _attr_name = "Charged peak"
    _attr_icon = "mdi:meter-electric"
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, cost_service, vat_mode):
        super().__init__(coordinator, entry, cost_service, "charged_peak")

    @property
    def native_value(self) -> float | None:
        bd = self._get_breakdown()
        if bd is not None:
            return round(bd.charged_peak_kw, 3)
        return self._restored_native_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        bd = self._get_breakdown()
        if bd is None:
            return attrs
        return {
            **attrs,
            "stored_peaks": [
                {"dt": p.dt.isoformat(), "kw": round(p.value / bd.peak_duration_hours, 3)}
                for p in bd.stored_peaks
            ],
            "peak_duration_hours": bd.peak_duration_hours,
        }
