"""TaxCostSensor — running tax cost for the current billing period."""

from __future__ import annotations

from .cost_sensor_base import CostSensorBase


class TaxCostSensor(CostSensorBase):
    _attr_name = "Tax cost"
    _attr_icon = "mdi:cash-minus"

    def __init__(self, coordinator, entry, cost_service, vat_mode):
        super().__init__(coordinator, entry, cost_service, "tax_cost")

    @property
    def native_value(self) -> float | None:
        bd = self._get_breakdown()
        if bd is not None:
            return round(bd.tax_cost, 2)
        return self._restored_native_value

    @property
    def native_unit_of_measurement(self) -> str:
        bd = self._get_breakdown()
        return bd.currency if bd is not None else "SEK"
