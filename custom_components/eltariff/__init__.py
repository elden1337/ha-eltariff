"""The eltariff integration."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .coordinator import EltariffCoordinator

    coordinator = EltariffCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register domain services once — guarded so multiple entries don't collide.
    if not hass.services.has_service(DOMAIN, "refresh"):
        async def handle_refresh(call) -> None:
            for coord in hass.data.get(DOMAIN, {}).values():
                await coord.async_request_refresh()

        hass.services.async_register(DOMAIN, "refresh", handle_refresh)

    if not hass.services.has_service(DOMAIN, "get_schedule"):
        async def handle_get_schedule(call) -> dict:
            from homeassistant.core import SupportsResponse  # noqa: F401 — imported for register call below
            from .api.schedule import build_day_schedule
            import zoneinfo

            raw_date = call.data.get("date")
            days = int(call.data.get("days", 1))
            start_day = date.fromisoformat(raw_date) if raw_date else date.today()

            # Use the first loaded coordinator — get_schedule targets a specific entry
            # via the service data in future; for now use the calling entry's coordinator.
            coord = hass.data[DOMAIN].get(entry.entry_id)
            if coord is None or coord.data is None:
                return {"schedule": []}

            tz = zoneinfo.ZoneInfo(coord.data.info.timezone or "Europe/Stockholm")
            tariff = coord.data.collection.get_tariff(coord.tariff_id)
            if tariff is None:
                return {"schedule": []}

            schedule = []
            for i in range(days):
                day = start_day + timedelta(days=i)
                slots = build_day_schedule(tariff, coord.data.collection, day, tz)
                for s in slots:
                    schedule.append({
                        "start": s.start.isoformat(),
                        "end": s.end.isoformat(),
                        "band": s.band_reference,
                        "price_inc_vat": s.price_inc_vat,
                        "currency": s.currency,
                    })

            return {"schedule": schedule}

        from homeassistant.core import SupportsResponse
        hass.services.async_register(
            DOMAIN,
            "get_schedule",
            handle_get_schedule,
            supports_response=SupportsResponse.OPTIONAL,
        )

    # Remove services only when the last entry is unloaded.
    def _maybe_remove_services() -> None:
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, "refresh")
            hass.services.async_remove(DOMAIN, "get_schedule")

    entry.async_on_unload(_maybe_remove_services)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
