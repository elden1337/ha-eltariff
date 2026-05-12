"""Sensor platform setup for the eltariff integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import CONF_VAT_MODE, DOMAIN, VAT_MODE_INC
from ..coordinator import EltariffCoordinator
from .active_power_band import ActivePowerBandSensor
from .active_power_price import ActivePowerPriceSensor
from .energy_price_total import EnergyPriceTotalSensor
from .energy_tax import EnergyTaxSensor
from .energy_transfer import EnergyTransferSensor
from .fixed_price_annual import FixedPriceAnnualSensor
from .next_transition import NextTransitionSensor
from .peaks_used_for_average import PeaksUsedForAverageSensor


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EltariffCoordinator = hass.data[DOMAIN][entry.entry_id]
    vat_mode = entry.options.get(CONF_VAT_MODE) or entry.data.get(CONF_VAT_MODE, VAT_MODE_INC)

    entities = [
        ActivePowerPriceSensor(coordinator, entry, vat_mode),
        ActivePowerBandSensor(coordinator, entry),
        EnergyPriceTotalSensor(coordinator, entry, vat_mode),
        EnergyTransferSensor(coordinator, entry, vat_mode),
        EnergyTaxSensor(coordinator, entry, vat_mode),
        FixedPriceAnnualSensor(coordinator, entry, vat_mode),
        PeaksUsedForAverageSensor(coordinator, entry),
        NextTransitionSensor(coordinator, entry),
    ]

    # Add the running cost sensor if an energy sensor (and thus CostService) is configured.
    cost_service = hass.data[DOMAIN].get(f"{entry.entry_id}_cost_service")
    if cost_service is not None:
        from .running_cost import RunningCostSensor

        entities.append(RunningCostSensor(coordinator, entry, cost_service, vat_mode))

    async_add_entities(entities)
