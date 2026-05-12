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


class RunningCostSensor(CoordinatorEntity[EltariffCoordinator], RestoreEntity, SensorEntity):
    """HA sensor whose state is the running cost for the billing period."""

    _attr_has_entity_name = True
    _attr_name = "Total running cost"
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
        self._breakdown_cache_key: int = -1
        self._breakdown = None

    @property
    def device_info(self):
        from homeassistant.helpers.entity import DeviceInfo

        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_cost")},
            name=f"{self._entry.title} Cost",
            via_device=(DOMAIN, self._entry.entry_id),
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

    def _get_breakdown(self):
        """Return breakdown, computed once per coordinator data object."""
        if self.coordinator.data is None:
            return None
        data_id = id(self.coordinator.data)
        if self._breakdown_cache_key != data_id:
            from datetime import UTC, datetime

            self._breakdown = self._cost_service.get_breakdown(
                datetime.now(tz=UTC), self.coordinator.data.snapshot
            )
            self._breakdown_cache_key = data_id
        return self._breakdown

    @property
    def native_value(self) -> float | None:
        bd = self._get_breakdown()
        return round(bd.total, 2) if bd is not None else None

    @property
    def native_unit_of_measurement(self) -> str:
        bd = self._get_breakdown()
        return bd.currency if bd is not None else "SEK"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        bd = self._get_breakdown()
        if bd is None:
            return {}

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
