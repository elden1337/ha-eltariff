"""PowerTracker — subscribes to a real-time power meter sensor and normalises readings to kW."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import POWER_UNIT_KW

_LOGGER = logging.getLogger(__name__)


class PowerTracker:
    """Listens to a HA sensor entity and exposes its reading normalised to kW.

    Used by the upcoming billing-period service layer to track peak consumption.
    States of 'unknown', 'unavailable', or non-numeric values are silently
    ignored and ``current_kw`` is set to ``None``.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str, unit: str) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._unit = unit
        self._current_kw: float | None = None

    @property
    def entity_id(self) -> str:
        """Entity ID of the tracked power sensor."""
        return self._entity_id

    @property
    def current_kw(self) -> float | None:
        """Latest reading normalised to kW, or None if unavailable."""
        return self._current_kw

    @callback
    def _on_state_change(self, event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable", ""):
            self._current_kw = None
            return

        try:
            value = float(new_state.state)
        except ValueError:
            _LOGGER.debug(
                "PowerTracker: non-numeric state '%s' from %s",
                new_state.state,
                self._entity_id,
            )
            self._current_kw = None
            return

        self._current_kw = value if self._unit == POWER_UNIT_KW else value / 1000.0
        _LOGGER.debug(
            "PowerTracker update: %.3f kW (raw %.3f %s)",
            self._current_kw,
            value,
            self._unit,
        )

    @callback
    def async_setup(self):
        """Register the state-change listener. Returns the cancel callback for cleanup."""
        _LOGGER.debug(
            "PowerTracker: subscribing to %s (unit=%s)",
            self._entity_id,
            self._unit,
        )
        return async_track_state_change_event(
            self._hass, [self._entity_id], self._on_state_change
        )
