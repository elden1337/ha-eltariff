"""EnergyTracker — subscribes to a cumulative energy sensor (kWh).

Replaces the former PowerTracker.  The tracked sensor should provide total
energy in kWh (e.g. a Riemann Sum integration helper or a native energy
meter).  State changes are forwarded to registered callbacks.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)


class EnergyTracker:
    """Listens to a HA energy sensor and exposes its reading in kWh."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._current_kwh: float | None = None
        self._callbacks: list[Callable[[float], None]] = []

    @property
    def entity_id(self) -> str:
        return self._entity_id

    @property
    def current_kwh(self) -> float | None:
        """Latest energy reading in kWh, or None if unavailable."""
        return self._current_kwh

    def on_update(self, cb: Callable[[float], None]) -> None:
        """Register a callback that fires with the new kWh value on each update."""
        self._callbacks.append(cb)

    @callback
    def _on_state_change(self, event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable", ""):
            self._current_kwh = None
            return

        try:
            value = float(new_state.state)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "EnergyTracker: non-numeric state '%s' from %s",
                new_state.state,
                self._entity_id,
            )
            self._current_kwh = None
            return

        self._current_kwh = value
        _LOGGER.debug("EnergyTracker update: %.3f kWh from %s", value, self._entity_id)
        for cb in self._callbacks:
            try:
                cb(value)
            except Exception:
                _LOGGER.exception("Error in EnergyTracker callback")

    @callback
    def async_setup(self):
        """Register the state-change listener. Returns the cancel callback."""
        _LOGGER.debug("EnergyTracker: subscribing to %s", self._entity_id)

        # Seed from the current state if available.
        state = self._hass.states.get(self._entity_id)
        if state and state.state not in ("unknown", "unavailable", ""):
            try:
                self._current_kwh = float(state.state)
            except (ValueError, TypeError):
                pass

        return async_track_state_change_event(self._hass, [self._entity_id], self._on_state_change)
