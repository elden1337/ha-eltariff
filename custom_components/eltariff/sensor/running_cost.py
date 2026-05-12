"""RunningCostSensor — single sensor exposing total running tariff cost.

State is the total running cost for the current billing period.
Attributes break the cost down into peak, transmission, tax and fixed
components, plus peak tracking metadata.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..billing.cost_service import CostService
from ..const import DOMAIN
from ..coordinator import EltariffCoordinator

_LOGGER = logging.getLogger(__name__)


class RunningCostSensor(
    CoordinatorEntity[EltariffCoordinator], RestoreEntity, SensorEntity
):
    """HA sensor whose state is the running cost for the billing period."""

    _attr_has_entity_name = True
    _attr_name = "Running cost"
    _attr_icon = "mdi:cash-clock"
    _attr_state_class = SensorStateClass.TOTAL
    _unrecorded_attributes = frozenset({"stored_peaks", "cost_service_state"})

    def __init__(
        self,
        coordinator: EltariffCoordinator,
        entry: ConfigEntry,
        cost_service: CostService,
        vat_mode: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._cost_service = cost_service
        self._vat_mode = vat_mode
        self._attr_unique_id = f"{entry.entry_id}_running_cost"

    @property
    def device_info(self):
        from homeassistant.helpers.entity import DeviceInfo

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
        )

    async def async_added_to_hass(self) -> None:
        """Restore state on startup."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state and last_state.attributes:
            saved = last_state.attributes.get("cost_service_state")
            if saved and isinstance(saved, dict):
                try:
                    self._cost_service.restore_state(saved)
                    _LOGGER.info("Restored running cost service state")
                except Exception:
                    _LOGGER.exception("Failed to restore cost service state")

    @property
    def native_value(self) -> float | None:
        snapshot = self.coordinator.data.snapshot if self.coordinator.data else None
        if snapshot is None:
            return None
        from datetime import UTC, datetime

        breakdown = self._cost_service.get_breakdown(
            datetime.now(tz=UTC), snapshot
        )
        return round(breakdown.total, 2)

    @property
    def native_unit_of_measurement(self) -> str:
        snapshot = self.coordinator.data.snapshot if self.coordinator.data else None
        if snapshot is None:
            return "SEK"
        from datetime import UTC, datetime

        breakdown = self._cost_service.get_breakdown(
            datetime.now(tz=UTC), snapshot
        )
        return breakdown.currency

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self.coordinator.data.snapshot if self.coordinator.data else None
        if snapshot is None:
            return {}

        from datetime import UTC, datetime

        now = datetime.now(tz=UTC)
        bd = self._cost_service.get_breakdown(now, snapshot)

        return {
            "peak_cost": round(bd.peak_cost, 4),
            "transmission_cost": round(bd.transmission_cost, 4),
            "tax_cost": round(bd.tax_cost, 4),
            "fixed_cost": round(bd.fixed_cost, 4),
            "observed_peak_kwh": round(bd.observed_peak_kwh, 4),
            "charged_peak_kwh": round(bd.charged_peak_kwh, 4),
            "total_energy_kwh": round(bd.total_energy_kwh, 4),
            "billing_period_start": (
                bd.billing_period_start.isoformat() if bd.billing_period_start else None
            ),
            "billing_period_end": (
                bd.billing_period_end.isoformat() if bd.billing_period_end else None
            ),
            "stored_peaks": [
                {"dt": p.dt.isoformat(), "kwh": round(p.value, 4)}
                for p in bd.stored_peaks
            ],
            "cost_service_state": self._cost_service.save_state(),
        }
