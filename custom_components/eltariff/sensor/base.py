"""Base sensor class for the eltariff integration."""
from __future__ import annotations

import zoneinfo
from datetime import date

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..coordinator import EltariffCoordinator
from ..coordinator_data import EltariffCoordinatorData


class EltariffSensorBase(CoordinatorEntity[EltariffCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EltariffCoordinator,
        entry: ConfigEntry,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"

    @property
    def _data(self) -> EltariffCoordinatorData:
        return self.coordinator.data

    def _last_updated_attr(self) -> dict:
        return {
            "last_updated_source": (
                self._data.info.tariff_data_last_updated.isoformat()
                if self._data.info.tariff_data_last_updated
                else None
            )
        }

    def _tariff_meta_attrs(self) -> dict:
        t = self._data.snapshot.tariff
        return {
            "tariff_id": t.id,
            "tariff_name": t.name,
            "valid_from": str(t.valid_period.from_including),
            "valid_to": str(t.valid_period.to_excluding),
            **self._last_updated_attr(),
        }

    def _today_schedule_attrs(self) -> dict:
        from ..api.schedule import build_day_schedule

        tz = zoneinfo.ZoneInfo(self._data.info.timezone or "Europe/Stockholm")
        tariff = self._data.collection.get_tariff(self.coordinator.tariff_id)
        if tariff is None:
            return {}
        slots = build_day_schedule(tariff, self._data.collection, date.today(), tz)
        return {
            "today_schedule": [
                {
                    "start": s.start.isoformat(),
                    "end": s.end.isoformat(),
                    "band": s.band_reference,
                    "price_inc_vat": s.price_inc_vat,
                }
                for s in slots
            ]
        }
