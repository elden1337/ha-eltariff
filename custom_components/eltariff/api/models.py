"""Dataclasses mirroring the RI-SE Grid Tariff API v0.3.x spec."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any


class CalendarPatternType(StrEnum):
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    HOLIDAYS = "holidays"


class ComponentType(StrEnum):
    FIXED = "fixed"
    PEAK = "peak"
    ENERGY = "energy"


@dataclass
class Price:
    price_ex_vat: float
    price_inc_vat: float
    currency: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Price:
        return cls(
            price_ex_vat=float(d["priceExVat"]),
            price_inc_vat=float(d["priceIncVat"]),
            currency=d["currency"],
        )


@dataclass
class ValidPeriod:
    from_including: date
    to_excluding: date | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ValidPeriod:
        return cls(
            from_including=date.fromisoformat(d["fromIncluding"]),
            to_excluding=date.fromisoformat(d["toExcluding"]) if d.get("toExcluding") else None,
        )

    def contains(self, dt: datetime) -> bool:
        if dt.date() < self.from_including:
            return False
        if self.to_excluding is not None and dt.date() >= self.to_excluding:
            return False
        return True


@dataclass
class CalendarPatternReferences:
    include: list[str]
    exclude: list[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalendarPatternReferences:
        return cls(
            include=list(d.get("include", [])),
            exclude=list(d.get("exclude", [])),
        )


@dataclass
class ActivePeriod:
    """A time-of-day band within a recurring period."""
    from_including: time
    to_excluding: time  # 00:00:00 when from_including != 00:00:00 means end-of-day
    calendar_pattern_references: CalendarPatternReferences

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ActivePeriod:
        return cls(
            from_including=time.fromisoformat(d["fromIncluding"]),
            to_excluding=time.fromisoformat(d["toExcluding"]),
            calendar_pattern_references=CalendarPatternReferences.from_dict(
                d.get("calendarPatternReferences", {})
            ),
        )

    def time_matches(self, dt: datetime) -> bool:
        t = dt.time().replace(second=0, microsecond=0)
        start = self.from_including
        end = self.to_excluding
        # Full-day convention: both are midnight
        if start == time(0, 0) and end == time(0, 0):
            return True
        # End-of-day convention: end is midnight but start is not
        if end == time(0, 0):
            return t >= start
        return start <= t < end


@dataclass
class RecurringPeriod:
    active_periods: list[ActivePeriod]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RecurringPeriod:
        return cls(
            active_periods=[ActivePeriod.from_dict(p) for p in d.get("activePeriods", [])]
        )


@dataclass
class PeakIdentificationSettings:
    number_of_peaks_for_average: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PeakIdentificationSettings:
        return cls(
            number_of_peaks_for_average=int(d["numberOfPeaksForAverageCalculation"])
        )


@dataclass
class PriceComponent:
    id: str
    reference: str
    component_type: ComponentType
    description: str
    valid_period: ValidPeriod
    price: Price
    recurring_periods: list[RecurringPeriod] = field(default_factory=list)
    peak_identification_settings: PeakIdentificationSettings | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PriceComponent:
        return cls(
            id=d["id"],
            reference=d.get("reference", ""),
            component_type=ComponentType(d["type"]),
            description=d.get("description", ""),
            valid_period=ValidPeriod.from_dict(d["validPeriod"]),
            price=Price.from_dict(d["price"]),
            recurring_periods=[RecurringPeriod.from_dict(r) for r in d.get("recurringPeriods", [])],
            peak_identification_settings=(
                PeakIdentificationSettings.from_dict(d["peakIdentificationSettings"])
                if "peakIdentificationSettings" in d
                else None
            ),
        )


@dataclass
class PriceGroup:
    components: list[PriceComponent]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PriceGroup:
        return cls(
            components=[PriceComponent.from_dict(c) for c in d.get("components", [])]
        )


@dataclass
class CalendarPattern:
    id: str
    name: str
    pattern_type: CalendarPatternType
    dates: list[date] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalendarPattern:
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            pattern_type=CalendarPatternType(d["type"]),
            dates=[date.fromisoformat(dt) for dt in d.get("dates", [])],
        )


@dataclass
class Tariff:
    id: str
    name: str
    product: str
    company_name: str
    valid_period: ValidPeriod
    fixed_price: PriceGroup | None = None
    energy_price: PriceGroup | None = None
    power_price: PriceGroup | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Tariff:
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            product=d.get("product", ""),
            company_name=d.get("companyName", ""),
            valid_period=ValidPeriod.from_dict(d["validPeriod"]),
            fixed_price=PriceGroup.from_dict(d["fixedPrice"]) if "fixedPrice" in d else None,
            energy_price=PriceGroup.from_dict(d["energyPrice"]) if "energyPrice" in d else None,
            power_price=PriceGroup.from_dict(d["powerPrice"]) if "powerPrice" in d else None,
        )


@dataclass
class TariffCollection:
    tariffs: list[Tariff]
    calendar_patterns: list[CalendarPattern]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TariffCollection:
        return cls(
            tariffs=[Tariff.from_dict(t) for t in d.get("tariffs", [])],
            calendar_patterns=[CalendarPattern.from_dict(p) for p in d.get("calendarPatterns", [])],
        )

    def get_tariff(self, tariff_id: str) -> Tariff | None:
        return next((t for t in self.tariffs if t.id == tariff_id), None)

    def get_calendar_pattern(self, pattern_id: str) -> CalendarPattern | None:
        return next((p for p in self.calendar_patterns if p.id == pattern_id), None)


@dataclass
class ServerInfo:
    timezone: str
    tariff_data_last_updated: datetime | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ServerInfo:
        raw_ts = d.get("tariffDataLastUpdated")
        return cls(
            timezone=d.get("timezone", "Europe/Stockholm"),
            tariff_data_last_updated=datetime.fromisoformat(raw_ts) if raw_ts else None,
        )


@dataclass
class ActiveTariffSnapshot:
    """Result of resolving which tariff components are active at a given moment."""
    at: datetime
    tariff: Tariff
    active_power_components: list[PriceComponent]
    active_energy_components: list[PriceComponent]
    active_fixed_components: list[PriceComponent]
    parse_warnings: list[str] = field(default_factory=list)

    @property
    def active_power_component(self) -> PriceComponent | None:
        return self.active_power_components[0] if self.active_power_components else None

    @property
    def total_energy_price_inc_vat(self) -> float:
        return sum(c.price.price_inc_vat for c in self.active_energy_components)

    @property
    def total_energy_price_ex_vat(self) -> float:
        return sum(c.price.price_ex_vat for c in self.active_energy_components)


@dataclass
class ScheduleSlot:
    """One contiguous time band in a day schedule."""
    start: datetime
    end: datetime
    band_reference: str
    price_inc_vat: float
    price_ex_vat: float
    currency: str
