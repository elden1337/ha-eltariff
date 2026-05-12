"""Diagnostics support for eltariff."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_BEARER_TOKEN, DOMAIN
from .coordinator import EltariffCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: EltariffCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    snap = data.snapshot

    sanitized_config = dict(entry.data)
    if CONF_BEARER_TOKEN in sanitized_config and sanitized_config[CONF_BEARER_TOKEN]:
        sanitized_config[CONF_BEARER_TOKEN] = "**REDACTED**"

    return {
        "config": sanitized_config,
        "server_info": {
            "timezone": data.info.timezone,
            "tariff_data_last_updated": (
                data.info.tariff_data_last_updated.isoformat()
                if data.info.tariff_data_last_updated
                else None
            ),
        },
        "active_snapshot": {
            "at": snap.at.isoformat(),
            "tariff_id": snap.tariff.id,
            "tariff_name": snap.tariff.name,
            "active_power_components": [c.id for c in snap.active_power_components],
            "active_energy_components": [c.id for c in snap.active_energy_components],
            "active_fixed_components": [c.id for c in snap.active_fixed_components],
            "parse_warnings": snap.parse_warnings,
        },
        "next_transition": (data.next_transition.isoformat() if data.next_transition else None),
        "calendar_patterns": [
            {"id": p.id, "name": p.name, "type": p.pattern_type}
            for p in data.collection.calendar_patterns
        ],
    }
