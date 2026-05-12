"""Shared base for cost-service-backed sensors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..billing.cost_service import CostService
from ..billing.models import CostBreakdown
from ..const import DOMAIN
from ..coordinator import EltariffCoordinator


class CostSensorBase(CoordinatorEntity[EltariffCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL

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

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_cost")},
            name=f"{self._entry.title} Cost",
            via_device=(DOMAIN, self._entry.entry_id),
        )

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
