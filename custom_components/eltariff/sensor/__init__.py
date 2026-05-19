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

    # Add price curve sensors for components that have a url (dynamic pricing).
    if coordinator.data and coordinator.data.price_curves:
        from .price_curve import PriceCurveSensor

        for comp_id in coordinator.data.price_curves:
            comp_name = _find_component_name(coordinator, comp_id)
            entities.append(
                PriceCurveSensor(coordinator, entry, vat_mode, comp_id, comp_name)
            )

    # Add cost-service sensors if an energy sensor (and thus CostService) is configured.
    cost_service = hass.data[DOMAIN].get(f"{entry.entry_id}_cost_service")
    if cost_service is not None:
        from .observed_peak import ObservedPeakSensor
        from .running_cost import RunningCostSensor
        from .tax_cost import TaxCostSensor
        from .transmission_cost import TransmissionCostSensor

        entities.extend([
            RunningCostSensor(coordinator, entry, cost_service, vat_mode),
            TaxCostSensor(coordinator, entry, cost_service, vat_mode),
            TransmissionCostSensor(coordinator, entry, cost_service, vat_mode),
            ObservedPeakSensor(coordinator, entry, cost_service, vat_mode),
        ])

        # Only spawn peak-cost and charged-peak sensors when the tariff has
        # an active power component (i.e. a traditional peak billing model).
        has_power = (
            coordinator.data
            and coordinator.data.snapshot
            and coordinator.data.snapshot.active_power_component is not None
        )
        if has_power:
            from .charged_peak import ChargedPeakSensor
            from .peak_cost import PeakCostSensor

            entities.extend([
                PeakCostSensor(coordinator, entry, cost_service, vat_mode),
                ChargedPeakSensor(coordinator, entry, cost_service, vat_mode),
            ])

        # Add price-curve running cost sensor when dynamic pricing components exist.
        has_price_curves = coordinator.data and coordinator.data.price_curves
        if has_price_curves:
            from .price_curve_cost import PriceCurveCostSensor

            entities.append(
                PriceCurveCostSensor(coordinator, entry, cost_service, vat_mode),
            )

    async_add_entities(entities)


def _find_component_name(coordinator: EltariffCoordinator, component_id: str) -> str | None:
    """Look up the human-readable name for a price-curve component."""
    if not coordinator.data or not coordinator.data.snapshot:
        return None
    tariff = coordinator.data.snapshot.tariff
    for group in (tariff.energy_price, tariff.power_price):
        if group is None:
            continue
        for comp in group.components:
            if comp.id == component_id:
                return comp.name
    return None
