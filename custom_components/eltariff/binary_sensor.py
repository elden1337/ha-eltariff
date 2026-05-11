"""Binary sensor entities for the eltariff integration."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.models import ComponentType
from .const import DOMAIN
from .coordinator import EltariffCoordinator, EltariffCoordinatorData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EltariffCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HighTariffActiveSensor(coordinator, entry)])


class HighTariffActiveSensor(CoordinatorEntity[EltariffCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "High tariff active"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: EltariffCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_high_tariff_active"

    @property
    def _data(self) -> EltariffCoordinatorData:
        return self.coordinator.data

    @property
    def is_on(self) -> bool:
        pc = self._data.snapshot.active_power_component
        return (
            pc is not None
            and pc.component_type == ComponentType.PEAK
            and pc.price.price_inc_vat > 0
        )

    @property
    def extra_state_attributes(self) -> dict:
        snap = self._data.snapshot
        t = snap.tariff
        return {
            "tariff_id": t.id,
            "tariff_name": t.name,
            "next_transition": (
                self._data.next_transition.isoformat()
                if self._data.next_transition
                else None
            ),
        }
