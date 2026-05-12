"""The eltariff integration."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from .const import CONF_ENERGY_SENSOR, CONF_VAT_MODE, DOMAIN, VAT_MODE_INC

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]


def _energy_entity_id(entry: ConfigEntry) -> str | None:
    return entry.options.get(CONF_ENERGY_SENSOR) or entry.data.get(CONF_ENERGY_SENSOR) or None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .coordinator import EltariffCoordinator

    coordinator = EltariffCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Set up energy tracker and cost service if an energy sensor is configured.
    energy_id = _energy_entity_id(entry)
    if energy_id:
        from .billing.cost_service import CostService
        from .energy_tracker import EnergyTracker

        vat_mode = entry.options.get(CONF_VAT_MODE) or entry.data.get(CONF_VAT_MODE, VAT_MODE_INC)

        cost_service = CostService()
        cost_service.vat_mode = vat_mode

        # Configure from the initial snapshot
        if coordinator.data and coordinator.data.snapshot:
            cost_service.configure_from_snapshot(coordinator.data.snapshot)

        tracker = EnergyTracker(hass, energy_id)

        def _on_energy(value: float) -> None:
            if coordinator.data and coordinator.data.snapshot:
                cost_service.on_energy_update(
                    reading_kwh=value,
                    now=datetime.now(tz=UTC),
                    snapshot=coordinator.data.snapshot,
                )

        tracker.on_update(_on_energy)

        hass.data[DOMAIN][f"{entry.entry_id}_tracker"] = tracker
        hass.data[DOMAIN][f"{entry.entry_id}_cost_service"] = cost_service
        entry.async_on_unload(tracker.async_setup())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload this entry whenever options are saved so the tracker and VAT mode
    # are updated without requiring a manual restart.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Register domain services once — guarded so multiple entries don't collide.
    if not hass.services.has_service(DOMAIN, "refresh"):

        async def handle_refresh(call) -> None:
            for coord in hass.data.get(DOMAIN, {}).values():
                await coord.async_request_refresh()

        hass.services.async_register(DOMAIN, "refresh", handle_refresh)

    if not hass.services.has_service(DOMAIN, "get_schedule"):

        async def handle_get_schedule(call) -> dict:
            import zoneinfo

            from homeassistant.core import SupportsResponse  # noqa: F401

            from .api.schedule import build_day_schedule

            raw_date = call.data.get("date")
            days = int(call.data.get("days", 1))
            start_day = date.fromisoformat(raw_date) if raw_date else date.today()

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
                    schedule.append(
                        {
                            "start": s.start.isoformat(),
                            "end": s.end.isoformat(),
                            "band": s.band_reference,
                            "price_inc_vat": s.price_inc_vat,
                            "currency": s.currency,
                        }
                    )

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


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so VAT mode, bearer token and energy tracker are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_tracker", None)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_cost_service", None)
    return unloaded
