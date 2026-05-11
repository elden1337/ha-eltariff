"""Sensor entities for the eltariff integration."""
from __future__ import annotations

import zoneinfo
from datetime import date, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_VAT_MODE, DOMAIN, VAT_MODE_INC
from .coordinator import EltariffCoordinator, EltariffCoordinatorData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EltariffCoordinator = hass.data[DOMAIN][entry.entry_id]
    vat_mode = entry.data.get(CONF_VAT_MODE, VAT_MODE_INC)

    async_add_entities([
        ActivePowerPriceSensor(coordinator, entry, vat_mode),
        ActivePowerBandSensor(coordinator, entry),
        EnergyPriceTotalSensor(coordinator, entry, vat_mode),
        EnergyTransferSensor(coordinator, entry, vat_mode),
        EnergyTaxSensor(coordinator, entry, vat_mode),
        FixedPriceAnnualSensor(coordinator, entry, vat_mode),
        PeaksUsedForAverageSensor(coordinator, entry),
        NextTransitionSensor(coordinator, entry),
    ])


class _EltariffSensorBase(CoordinatorEntity[EltariffCoordinator], SensorEntity):
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

    def _common_attrs(self) -> dict:
        from .api.schedule import build_day_schedule

        snap = self._data.snapshot
        t = snap.tariff
        attrs: dict = {
            "tariff_id": t.id,
            "tariff_name": t.name,
            "product": t.product,
            "company_name": t.company_name,
            "valid_from": str(t.valid_period.from_including),
            "valid_to": str(t.valid_period.to_excluding),
            "last_updated_source": (
                self._data.info.tariff_data_last_updated.isoformat()
                if self._data.info.tariff_data_last_updated
                else None
            ),
        }
        tz = zoneinfo.ZoneInfo(self.coordinator.data.info.timezone or "Europe/Stockholm")
        tariff = self.coordinator.data.collection.get_tariff(self.coordinator.tariff_id)
        if tariff is not None:
            slots = build_day_schedule(tariff, self.coordinator.data.collection, date.today(), tz)
            attrs["today_schedule"] = [
                {
                    "start": s.start.isoformat(),
                    "end": s.end.isoformat(),
                    "band": s.band_reference,
                    "price_inc_vat": s.price_inc_vat,
                }
                for s in slots
            ]
        return attrs


class ActivePowerPriceSensor(_EltariffSensorBase):
    _attr_name = "Active power price"
    _attr_icon = "mdi:transmission-tower"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, vat_mode: str) -> None:
        super().__init__(coordinator, entry, "active_power_price")
        self._vat_mode = vat_mode

    @property
    def native_value(self) -> float | None:
        pc = self._data.snapshot.active_power_component
        if pc is None:
            return None
        return pc.price.price_inc_vat if self._vat_mode == VAT_MODE_INC else pc.price.price_ex_vat

    @property
    def native_unit_of_measurement(self) -> str | None:
        pc = self._data.snapshot.active_power_component
        return f"{pc.price.currency}/kW" if pc else None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = self._common_attrs()
        pc = self._data.snapshot.active_power_component
        if pc:
            attrs["reference"] = pc.reference
            attrs["currency"] = pc.price.currency
        return attrs


class ActivePowerBandSensor(_EltariffSensorBase):
    _attr_name = "Active power band"
    _attr_icon = "mdi:clock-time-four-outline"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "active_power_band")

    @property
    def native_value(self) -> str | None:
        pc = self._data.snapshot.active_power_component
        return pc.reference if pc else None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = self._common_attrs()
        attrs["parse_warnings"] = self._data.snapshot.parse_warnings
        return attrs


class EnergyPriceTotalSensor(_EltariffSensorBase):
    _attr_name = "Energy price total"
    _attr_icon = "mdi:lightning-bolt"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, vat_mode: str) -> None:
        super().__init__(coordinator, entry, "energy_price_total")
        self._vat_mode = vat_mode

    @property
    def native_value(self) -> float:
        snap = self._data.snapshot
        if self._vat_mode == VAT_MODE_INC:
            return snap.total_energy_price_inc_vat
        return snap.total_energy_price_ex_vat

    @property
    def native_unit_of_measurement(self) -> str:
        comps = self._data.snapshot.active_energy_components
        currency = comps[0].price.currency if comps else "SEK"
        return f"{currency}/kWh"

    @property
    def extra_state_attributes(self) -> dict:
        return self._common_attrs()


class EnergyTransferSensor(_EltariffSensorBase):
    _attr_name = "Energy transfer price"
    _attr_icon = "mdi:transmission-tower-export"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, vat_mode: str) -> None:
        super().__init__(coordinator, entry, "energy_transfer")
        self._vat_mode = vat_mode

    @property
    def native_value(self) -> float | None:
        comps = [c for c in self._data.snapshot.active_energy_components if c.reference == "main"]
        if not comps:
            return None
        p = comps[0].price
        return p.price_inc_vat if self._vat_mode == VAT_MODE_INC else p.price_ex_vat

    @property
    def native_unit_of_measurement(self) -> str:
        comps = self._data.snapshot.active_energy_components
        currency = comps[0].price.currency if comps else "SEK"
        return f"{currency}/kWh"

    @property
    def extra_state_attributes(self) -> dict:
        return self._common_attrs()


class EnergyTaxSensor(_EltariffSensorBase):
    _attr_name = "Energy tax"
    _attr_icon = "mdi:percent"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, vat_mode: str) -> None:
        super().__init__(coordinator, entry, "energy_tax")
        self._vat_mode = vat_mode

    @property
    def native_value(self) -> float | None:
        comps = [c for c in self._data.snapshot.active_energy_components if c.reference == "tax"]
        if not comps:
            return None
        p = comps[0].price
        return p.price_inc_vat if self._vat_mode == VAT_MODE_INC else p.price_ex_vat

    @property
    def native_unit_of_measurement(self) -> str:
        comps = self._data.snapshot.active_energy_components
        currency = comps[0].price.currency if comps else "SEK"
        return f"{currency}/kWh"

    @property
    def extra_state_attributes(self) -> dict:
        return self._common_attrs()


class FixedPriceAnnualSensor(_EltariffSensorBase):
    _attr_name = "Fixed price annual"
    _attr_icon = "mdi:calendar-month"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, vat_mode: str) -> None:
        super().__init__(coordinator, entry, "fixed_price_annual")
        self._vat_mode = vat_mode

    @property
    def native_value(self) -> float | None:
        comps = self._data.snapshot.active_fixed_components
        if not comps:
            return None
        return sum(
            c.price.price_inc_vat if self._vat_mode == VAT_MODE_INC else c.price.price_ex_vat
            for c in comps
        )

    @property
    def native_unit_of_measurement(self) -> str:
        comps = self._data.snapshot.active_fixed_components
        currency = comps[0].price.currency if comps else "SEK"
        return f"{currency}/year"

    @property
    def extra_state_attributes(self) -> dict:
        return self._common_attrs()


class PeaksUsedForAverageSensor(_EltariffSensorBase):
    _attr_name = "Peaks used for average"
    _attr_icon = "mdi:chart-bar"
    _attr_native_unit_of_measurement = "peaks"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "peaks_used_for_average")

    @property
    def native_value(self) -> int | None:
        pc = self._data.snapshot.active_power_component
        if pc and pc.peak_identification_settings:
            return pc.peak_identification_settings.number_of_peaks_for_average
        return None

    @property
    def extra_state_attributes(self) -> dict:
        return self._common_attrs()


class NextTransitionSensor(_EltariffSensorBase):
    _attr_name = "Next tariff transition"
    _attr_icon = "mdi:clock-fast"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "next_transition")

    @property
    def native_value(self) -> datetime | None:
        return self._data.next_transition

    @property
    def extra_state_attributes(self) -> dict:
        return self._common_attrs()
