"""PriceCurveSensor — exposes hourly grid tariff price curves."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry

from ..const import VAT_MODE_INC
from ..coordinator import EltariffCoordinator
from .base import EltariffSensorBase


class PriceCurveSensor(EltariffSensorBase):
    """Sensor for a dynamic price curve component.

    native_value: current hour's price from the curve.
    Attributes expose the full today and tomorrow curves so HA automations
    can plan ahead.
    """

    _attr_icon = "mdi:chart-timeline-variant"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: EltariffCoordinator,
        entry: ConfigEntry,
        vat_mode: str,
        component_id: str,
        component_name: str | None = None,
    ) -> None:
        suffix = f"price_curve_{component_id[:8]}"
        super().__init__(coordinator, entry, suffix)
        self._vat_mode = vat_mode
        self._component_id = component_id
        self._attr_name = f"Price curve {component_name or component_id[:8]}"

    @property
    def _prices_response(self):
        curves = self._data.price_curves
        return curves.get(self._component_id) if curves else None

    @property
    def native_value(self) -> float | None:
        resp = self._prices_response
        if resp is None:
            return None
        snap_time = self._data.snapshot.at
        entry = resp.entry_at(snap_time)
        if entry is None:
            return None
        return entry.price_inc_vat if self._vat_mode == VAT_MODE_INC else entry.price_ex_vat

    @property
    def native_unit_of_measurement(self) -> str:
        resp = self._prices_response
        currency = resp.currency if resp else "SEK"
        return f"{currency}/kWh"

    def _entries_as_dicts(self, entries) -> list[dict]:
        return [
            {
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
                "price_ex_vat": e.price_ex_vat,
                "price_inc_vat": e.price_inc_vat,
            }
            for e in entries
        ]

    @property
    def extra_state_attributes(self) -> dict:
        resp = self._prices_response
        if resp is None:
            return {
                **self._last_updated_attr(),
                "today": [],
                "tomorrow": [],
                "tomorrow_available": False,
            }

        snap_time = self._data.snapshot.at
        today = snap_time.date()
        tomorrow = today + timedelta(days=1)

        today_entries = resp.entries_for_date(today)
        tomorrow_entries = resp.entries_for_date(tomorrow)

        return {
            **self._last_updated_attr(),
            "component_id": self._component_id,
            "resolution": resp.resolution,
            "today": self._entries_as_dicts(today_entries),
            "tomorrow": self._entries_as_dicts(tomorrow_entries),
            "tomorrow_available": len(tomorrow_entries) > 0,
        }
