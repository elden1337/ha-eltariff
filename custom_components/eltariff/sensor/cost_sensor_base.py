"""Shared base for cost-service-backed sensors."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..billing.cost_service import CostService
from ..billing.models import CostBreakdown
from ..const import DOMAIN
from ..coordinator import EltariffCoordinator

_LOGGER = logging.getLogger(__name__)


class CostSensorBase(CoordinatorEntity[EltariffCoordinator], RestoreEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _unrecorded_attributes = frozenset({"cost_service_state"})

    def __init__(
        self,
        coordinator: EltariffCoordinator,
        entry: ConfigEntry,
        cost_service: CostService,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._cost_service = cost_service
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._breakdown_cache_key: int = -1
        self._breakdown: CostBreakdown | None = None
        self._restored_native_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore CostService state and last native value on startup."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if not last_state:
            return

        # Cache the last known native value as a fallback until the first
        # coordinator update produces a fresh breakdown.
        if last_state.state not in (None, "unknown", "unavailable"):
            try:
                self._restored_native_value = float(last_state.state)
            except (ValueError, TypeError):
                pass

        # Attempt to restore the shared CostService state.  Multiple cost
        # sensors may each try this; the data is identical so the last
        # write wins harmlessly.
        if last_state.attributes:
            saved = last_state.attributes.get("cost_service_state")
            if saved and isinstance(saved, dict):
                try:
                    self._cost_service.restore_state(saved)
                    _LOGGER.info(
                        "Restored cost service state from %s", self._attr_unique_id
                    )
                except Exception:
                    _LOGGER.exception(
                        "Failed to restore cost service state from %s",
                        self._attr_unique_id,
                    )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_cost")},
            name=f"{self._entry.title} Cost",
            via_device=(DOMAIN, self._entry.entry_id),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "cost_service_state": self._cost_service.save_state(),
        }

    def _get_breakdown(self) -> CostBreakdown | None:
        if self.coordinator.data is None:
            return None
        data_id = id(self.coordinator.data)
        if self._breakdown_cache_key != data_id:
            self._breakdown = self._cost_service.get_breakdown(
                datetime.now(tz=UTC), self.coordinator.data.snapshot
            )
            self._breakdown_cache_key = data_id
        return self._breakdown
