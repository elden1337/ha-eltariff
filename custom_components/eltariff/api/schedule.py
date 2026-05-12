"""Pure schedule resolution: which tariff components are active at a given datetime."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from .models import (
    ActivePeriod,
    ActiveTariffSnapshot,
    CalendarPattern,
    CalendarPatternType,
    PriceComponent,
    PriceGroup,
    ScheduleSlot,
    Tariff,
    TariffCollection,
)

_LOGGER = logging.getLogger(__name__)


def _calendar_pattern_matches(
    pattern: CalendarPattern,
    dt: datetime,
) -> bool:
    match pattern.pattern_type:
        case CalendarPatternType.WEEKDAYS:
            return dt.isoweekday() <= 5
        case CalendarPatternType.WEEKENDS:
            return dt.isoweekday() >= 6
        case CalendarPatternType.HOLIDAYS:
            return dt.date() in pattern.dates
    return False


def _active_period_matches(
    active_period: ActivePeriod,
    dt: datetime,
    collection: TariffCollection,
) -> bool:
    if not active_period.time_matches(dt):
        return False

    refs = active_period.calendar_pattern_references

    if refs.include:
        included = any(
            (p := collection.get_calendar_pattern(pid)) is not None
            and _calendar_pattern_matches(p, dt)
            for pid in refs.include
        )
        if not included:
            return False

    for pid in refs.exclude:
        p = collection.get_calendar_pattern(pid)
        if p is not None and _calendar_pattern_matches(p, dt):
            return False

    return True


def _component_active(
    component: PriceComponent,
    dt: datetime,
    collection: TariffCollection,
) -> bool:
    if not component.valid_period.contains(dt):
        return False

    if not component.recurring_periods:
        return True

    return any(
        any(_active_period_matches(ap, dt, collection) for ap in rp.active_periods)
        for rp in component.recurring_periods
    )


def _resolve_group(
    group: PriceGroup | None,
    dt: datetime,
    collection: TariffCollection,
    label: str,
    warnings: list[str],
) -> list[PriceComponent]:
    if group is None:
        return []

    active = [c for c in group.components if _component_active(c, dt, collection)]

    refs = {c.reference for c in active}
    for ref in refs:
        count = sum(1 for c in active if c.reference == ref)
        if count > 1:
            warnings.append(
                f"{label}: {count} components with reference={ref!r} active simultaneously"
            )

    return active


def resolve_active_components(
    tariff: Tariff,
    collection: TariffCollection,
    at: datetime,
) -> ActiveTariffSnapshot:
    """Return which components are active at *at*."""
    warnings: list[str] = []

    power = _resolve_group(tariff.power_price, at, collection, "powerPrice", warnings)
    energy = _resolve_group(tariff.energy_price, at, collection, "energyPrice", warnings)
    fixed = _resolve_group(tariff.fixed_price, at, collection, "fixedPrice", warnings)

    if tariff.power_price and len(tariff.power_price.components) > 0 and not power:
        warnings.append("powerPrice: no active component found")

    return ActiveTariffSnapshot(
        at=at,
        tariff=tariff,
        active_power_components=power,
        active_energy_components=energy,
        active_fixed_components=fixed,
        parse_warnings=warnings,
    )


def next_transition_at(
    tariff: Tariff,
    collection: TariffCollection,
    after: datetime,
    horizon: timedelta = timedelta(hours=48),
) -> datetime | None:
    """Return the next datetime after *after* when the active component set changes.

    Scans minute-by-minute within *horizon*. Intentionally simple — tariff data
    changes infrequently, so this runs only once per snapshot update.
    """
    current = resolve_active_components(tariff, collection, after)
    current_ids = {
        c.id
        for c in (
            current.active_power_components
            + current.active_energy_components
            + current.active_fixed_components
        )
    }

    # Advance to the start of the next minute for clean boundaries.
    t = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = after + horizon

    while t <= end:
        snap = resolve_active_components(tariff, collection, t)
        ids = {
            c.id
            for c in (
                snap.active_power_components
                + snap.active_energy_components
                + snap.active_fixed_components
            )
        }
        if ids != current_ids:
            return t
        t += timedelta(minutes=1)

    return None


def build_day_schedule(
    tariff: Tariff,
    collection: TariffCollection,
    day: date,
    tz_info,
) -> list[ScheduleSlot]:
    """Return hour-by-hour schedule slots for *day*."""
    slots: list[ScheduleSlot] = []

    t = datetime(day.year, day.month, day.day, 0, 0, tzinfo=tz_info)
    end = t + timedelta(days=1)

    while t < end:
        slot_end = t + timedelta(hours=1)
        snap = resolve_active_components(tariff, collection, t)
        pc = snap.active_power_component

        if pc:
            slots.append(
                ScheduleSlot(
                    start=t,
                    end=slot_end,
                    band_reference=pc.reference,
                    price_inc_vat=pc.price.price_inc_vat,
                    price_ex_vat=pc.price.price_ex_vat,
                    currency=pc.price.currency,
                )
            )
        t = slot_end

    return slots
