"""PriceCurveCostSensor — running price-curve cost for the current billing period."""

from __future__ import annotations

from .cost_sensor_base import CostSensorBase


class PriceCurveCostSensor(CostSensorBase):
    _attr_name = "Price curve cost"
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, coordinator, entry, cost_service, vat_mode):
        super().__init__(coordinator, entry, cost_service, "price_curve_cost")

    @property
    def native_value(self) -> float | None:
        bd = self._get_breakdown()
        if bd is not None:
            return round(bd.price_curve_cost, 2)
        return self._restored_native_value

    @property
    def native_unit_of_measurement(self) -> str:
        bd = self._get_breakdown()
        return bd.currency if bd is not None else "SEK"
