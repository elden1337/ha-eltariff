"""RunningCostSensor — single sensor exposing total running tariff cost.

State is the total running cost for the current billing period.
Attributes break the cost down into peak, transmission, tax and fixed
components, plus peak tracking metadata.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from ..billing.cost_service import CostService
from ..coordinator import EltariffCoordinator
from .cost_sensor_base import CostSensorBase


class RunningCostSensor(CostSensorBase):
    """HA sensor whose state is the running cost for the billing period."""

    _attr_name = "Total running cost"
    _attr_icon = "mdi:cash-clock"
    _unrecorded_attributes = frozenset({"stored_peaks", "cost_service_state"})

    def __init__(
        self,
        coordinator: EltariffCoordinator,
        entry: ConfigEntry,
        cost_service: CostService,
        vat_mode: str,
    ) -> None:
        super().__init__(coordinator, entry, cost_service, "running_cost")

    @property
    def native_value(self) -> float | None:
        bd = self._get_breakdown()
        if bd is not None:
            return round(bd.total, 2)
        return self._restored_native_value

    @property
    def native_unit_of_measurement(self) -> str:
        bd = self._get_breakdown()
        return bd.currency if bd is not None else "SEK"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        bd = self._get_breakdown()
        if bd is None:
            return super().extra_state_attributes

        return {
            "peak_cost": round(bd.peak_cost, 4),
            "transmission_cost": round(bd.transmission_cost, 4),
            "tax_cost": round(bd.tax_cost, 4),
            "fixed_cost": round(bd.fixed_cost, 4),
            "total_energy_kwh": round(bd.total_energy_kwh, 4),
            "billing_period_start": (
                bd.billing_period_start.isoformat() if bd.billing_period_start else None
            ),
            "billing_period_end": (
                bd.billing_period_end.isoformat() if bd.billing_period_end else None
            ),
            "cost_service_state": self._cost_service.save_state(),
        }
