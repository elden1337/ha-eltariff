"""Advanced schedule resolution tests.

Covers: _calendar_pattern_matches, _active_period_matches, _component_active,
resolve_active_components (energy/fixed, duplicate warnings, no-match warning,
expired components), next_transition_at, build_day_schedule.
"""

from __future__ import annotations

import zoneinfo
from datetime import UTC, date, datetime, time, timedelta

import pytest

from custom_components.eltariff.api.models import (
    ActivePeriod,
    CalendarPattern,
    CalendarPatternReferences,
    CalendarPatternType,
    ComponentType,
    PeakIdentificationSettings,
    Price,
    PriceComponent,
    PriceGroup,
    RecurringPeriod,
    Tariff,
    TariffCollection,
    ValidPeriod,
)
from custom_components.eltariff.api.schedule import (
    _active_period_matches,
    _calendar_pattern_matches,
    _component_active,
    build_day_schedule,
    next_transition_at,
    resolve_active_components,
)


# ── Shared helpers ─────────────────────────────────────────────────────────────


def _price(value: float = 1.0, currency: str = "SEK") -> Price:
    return Price(price_ex_vat=value * 0.8, price_inc_vat=value, currency=currency)


def _vp(from_: date = date(2025, 1, 1), to: date | None = date(2026, 1, 1)) -> ValidPeriod:
    return ValidPeriod(from_including=from_, to_excluding=to)


def _refs(
    include: list[str] | None = None, exclude: list[str] | None = None
) -> CalendarPatternReferences:
    return CalendarPatternReferences(include=include or [], exclude=exclude or [])


def _ap(
    start: time, end: time, include: list[str] | None = None, exclude: list[str] | None = None
) -> ActivePeriod:
    return ActivePeriod(
        from_including=start, to_excluding=end, calendar_pattern_references=_refs(include, exclude)
    )


def _weekday_pat(id_: str = "wd") -> CalendarPattern:
    return CalendarPattern(id=id_, name="Weekdays", pattern_type=CalendarPatternType.WEEKDAYS)


def _weekend_pat(id_: str = "we") -> CalendarPattern:
    return CalendarPattern(id=id_, name="Weekends", pattern_type=CalendarPatternType.WEEKENDS)


def _holiday_pat(dates: list[date], id_: str = "hol") -> CalendarPattern:
    return CalendarPattern(
        id=id_, name="Holidays", pattern_type=CalendarPatternType.HOLIDAYS, dates=dates
    )


def _component(
    id_: str,
    ref: str,
    ctype: ComponentType = ComponentType.PEAK,
    price_val: float = 1.0,
    active_periods: list[ActivePeriod] | None = None,
    vp: ValidPeriod | None = None,
) -> PriceComponent:
    rps = [RecurringPeriod(active_periods=active_periods)] if active_periods else []
    return PriceComponent(
        id=id_,
        reference=ref,
        component_type=ctype,
        description="",
        valid_period=vp or _vp(),
        price=_price(price_val),
        recurring_periods=rps,
    )


def _tariff(
    power_price: PriceGroup | None = None,
    energy_price: PriceGroup | None = None,
    fixed_price: PriceGroup | None = None,
) -> Tariff:
    return Tariff(
        id="t1",
        name="Test",
        product="P",
        company_name="AB",
        valid_period=_vp(),
        power_price=power_price,
        energy_price=energy_price,
        fixed_price=fixed_price,
    )


def _collection(
    patterns: list[CalendarPattern] | None = None, tariff: Tariff | None = None
) -> TariffCollection:
    return TariffCollection(tariffs=[tariff or _tariff()], calendar_patterns=patterns or [])


# ── _calendar_pattern_matches ──────────────────────────────────────────────────


class TestCalendarPatternMatches:
    # Weekdays (Mon=1 … Fri=5)
    def test_weekday_monday(self) -> None:
        assert _calendar_pattern_matches(_weekday_pat(), datetime(2025, 1, 6, 9, tzinfo=UTC))

    def test_weekday_friday(self) -> None:
        assert _calendar_pattern_matches(_weekday_pat(), datetime(2025, 1, 10, 9, tzinfo=UTC))

    def test_weekday_saturday_false(self) -> None:
        assert not _calendar_pattern_matches(_weekday_pat(), datetime(2025, 1, 11, 9, tzinfo=UTC))

    def test_weekday_sunday_false(self) -> None:
        assert not _calendar_pattern_matches(_weekday_pat(), datetime(2025, 1, 12, 9, tzinfo=UTC))

    # Weekends (Sat=6, Sun=7)
    def test_weekend_saturday(self) -> None:
        assert _calendar_pattern_matches(_weekend_pat(), datetime(2025, 1, 11, 9, tzinfo=UTC))

    def test_weekend_sunday(self) -> None:
        assert _calendar_pattern_matches(_weekend_pat(), datetime(2025, 1, 12, 9, tzinfo=UTC))

    def test_weekend_monday_false(self) -> None:
        assert not _calendar_pattern_matches(_weekend_pat(), datetime(2025, 1, 6, 9, tzinfo=UTC))

    # Holidays
    def test_holiday_matching_date(self) -> None:
        pat = _holiday_pat([date(2025, 1, 1)])
        assert _calendar_pattern_matches(pat, datetime(2025, 1, 1, 10, tzinfo=UTC))

    def test_holiday_non_matching_date(self) -> None:
        pat = _holiday_pat([date(2025, 1, 1)])
        assert not _calendar_pattern_matches(pat, datetime(2025, 1, 2, 10, tzinfo=UTC))

    def test_holiday_empty_dates_never_matches(self) -> None:
        assert not _calendar_pattern_matches(_holiday_pat([]), datetime(2025, 6, 5, 10, tzinfo=UTC))

    def test_holiday_day_in_list(self) -> None:
        pat = _holiday_pat([date(2025, 12, 25), date(2025, 12, 26)])
        assert _calendar_pattern_matches(pat, datetime(2025, 12, 25, 15, tzinfo=UTC))
        assert _calendar_pattern_matches(pat, datetime(2025, 12, 26, 15, tzinfo=UTC))
        assert not _calendar_pattern_matches(pat, datetime(2025, 12, 27, 15, tzinfo=UTC))


# ── _active_period_matches ─────────────────────────────────────────────────────


class TestActivePeriodMatches:
    def _coll(self, patterns: list[CalendarPattern] | None = None) -> TariffCollection:
        return TariffCollection(tariffs=[], calendar_patterns=patterns or [])

    # Time-only (no include/exclude)
    def test_no_refs_time_in_range(self) -> None:
        ap = _ap(time(7, 0), time(20, 0))
        assert _active_period_matches(ap, datetime(2025, 1, 6, 9, tzinfo=UTC), self._coll())

    def test_no_refs_time_out_of_range(self) -> None:
        ap = _ap(time(7, 0), time(20, 0))
        assert not _active_period_matches(ap, datetime(2025, 1, 6, 6, tzinfo=UTC), self._coll())

    def test_time_mismatch_short_circuits_regardless_of_patterns(self) -> None:
        # Even though the weekday pattern matches (Monday), time is wrong → False
        ap = _ap(time(7, 0), time(20, 0), include=["wd"])
        coll = self._coll([_weekday_pat()])
        assert not _active_period_matches(ap, datetime(2025, 1, 6, 6, tzinfo=UTC), coll)

    # include list
    def test_include_matching_pattern_allows(self) -> None:
        ap = _ap(time(0, 0), time(0, 0), include=["wd"])
        coll = self._coll([_weekday_pat()])
        assert _active_period_matches(ap, datetime(2025, 1, 6, 10, tzinfo=UTC), coll)  # Monday

    def test_include_non_matching_day_denies(self) -> None:
        ap = _ap(time(0, 0), time(0, 0), include=["wd"])
        coll = self._coll([_weekday_pat()])
        assert not _active_period_matches(
            ap, datetime(2025, 1, 11, 10, tzinfo=UTC), coll
        )  # Saturday

    def test_unknown_include_id_denies(self) -> None:
        ap = _ap(time(0, 0), time(0, 0), include=["nonexistent"])
        assert not _active_period_matches(ap, datetime(2025, 1, 6, 10, tzinfo=UTC), self._coll())

    def test_include_multiple_patterns_any_match_allows(self) -> None:
        ap = _ap(time(0, 0), time(0, 0), include=["wd", "we"])
        coll = self._coll([_weekday_pat(), _weekend_pat()])
        # Both a weekday and a weekend should be allowed
        assert _active_period_matches(ap, datetime(2025, 1, 6, 10, tzinfo=UTC), coll)  # Monday
        assert _active_period_matches(ap, datetime(2025, 1, 11, 10, tzinfo=UTC), coll)  # Saturday

    # exclude list
    def test_exclude_matching_pattern_denies(self) -> None:
        ap = _ap(time(0, 0), time(0, 0), include=["wd"], exclude=["hol"])
        hol = date(2025, 1, 6)  # Monday that is also a holiday
        coll = self._coll([_weekday_pat(), _holiday_pat([hol])])
        assert not _active_period_matches(ap, datetime(2025, 1, 6, 10, tzinfo=UTC), coll)

    def test_exclude_non_matching_pattern_allows(self) -> None:
        ap = _ap(time(0, 0), time(0, 0), include=["wd"], exclude=["hol"])
        coll = self._coll([_weekday_pat(), _holiday_pat([])])
        # Jan 7 is a regular Tuesday, no holiday → not excluded
        assert _active_period_matches(ap, datetime(2025, 1, 7, 10, tzinfo=UTC), coll)

    def test_unknown_exclude_id_is_no_op(self) -> None:
        ap = _ap(time(0, 0), time(0, 0), exclude=["nonexistent"])
        # Unknown exclude pattern → no match → not excluded
        assert _active_period_matches(ap, datetime(2025, 1, 6, 10, tzinfo=UTC), self._coll())

    def test_full_day_any_time_with_include(self) -> None:
        ap = _ap(time(0, 0), time(0, 0), include=["we"])
        coll = self._coll([_weekend_pat()])
        assert _active_period_matches(
            ap, datetime(2025, 1, 11, 0, tzinfo=UTC), coll
        )  # Saturday midnight
        assert _active_period_matches(ap, datetime(2025, 1, 11, 23, 59, tzinfo=UTC), coll)


# ── _component_active ──────────────────────────────────────────────────────────


class TestComponentActive:
    def _coll(self) -> TariffCollection:
        return TariffCollection(tariffs=[], calendar_patterns=[])

    def test_no_recurring_periods_always_active_within_valid_period(self) -> None:
        comp = PriceComponent(
            id="f1",
            reference="fee",
            component_type=ComponentType.FIXED,
            description="",
            valid_period=_vp(),
            price=_price(),
            recurring_periods=[],
        )
        assert _component_active(comp, datetime(2025, 6, 1, 12, tzinfo=UTC), self._coll())

    def test_no_recurring_periods_outside_valid_period_false(self) -> None:
        comp = PriceComponent(
            id="f1",
            reference="fee",
            component_type=ComponentType.FIXED,
            description="",
            valid_period=_vp(to=date(2024, 1, 1)),
            price=_price(),
            recurring_periods=[],
        )
        assert not _component_active(comp, datetime(2025, 6, 1, 12, tzinfo=UTC), self._coll())

    def test_with_matching_recurring_period(self) -> None:
        comp = _component("c1", "band", active_periods=[_ap(time(0, 0), time(0, 0))])
        assert _component_active(comp, datetime(2025, 6, 1, 12, tzinfo=UTC), self._coll())

    def test_with_non_matching_recurring_period(self) -> None:
        # 07:00-20:00 only; query at midnight → not active
        comp = _component("c1", "band", active_periods=[_ap(time(7, 0), time(20, 0))])
        assert not _component_active(comp, datetime(2025, 6, 1, 0, tzinfo=UTC), self._coll())

    def test_any_recurring_period_match_is_sufficient(self) -> None:
        # Two RecurringPeriods; only second matches
        rp1 = RecurringPeriod(active_periods=[_ap(time(7, 0), time(12, 0))])
        rp2 = RecurringPeriod(active_periods=[_ap(time(12, 0), time(20, 0))])
        comp = PriceComponent(
            id="c1",
            reference="band",
            component_type=ComponentType.PEAK,
            description="",
            valid_period=_vp(),
            price=_price(),
            recurring_periods=[rp1, rp2],
        )
        assert _component_active(comp, datetime(2025, 6, 1, 15, tzinfo=UTC), self._coll())


# ── resolve_active_components ──────────────────────────────────────────────────


class TestResolveActiveComponents:
    def test_no_price_groups_returns_empty_snapshot(self) -> None:
        t = _tariff()
        coll = _collection(tariff=t)
        snap = resolve_active_components(t, coll, datetime(2025, 6, 2, 12, tzinfo=UTC))
        assert snap.active_power_components == []
        assert snap.active_energy_components == []
        assert snap.active_fixed_components == []
        assert snap.parse_warnings == []

    def test_power_component_active(self) -> None:
        comp = _component("c1", "band_a", active_periods=[_ap(time(0, 0), time(0, 0))])
        t = _tariff(power_price=PriceGroup(components=[comp]))
        coll = _collection(tariff=t)
        snap = resolve_active_components(t, coll, datetime(2025, 6, 2, 12, tzinfo=UTC))
        assert [c.reference for c in snap.active_power_components] == ["band_a"]

    def test_energy_components_both_active(self) -> None:
        transfer = _component(
            "main", "main", ComponentType.ENERGY, active_periods=[_ap(time(0, 0), time(0, 0))]
        )
        tax = _component(
            "tax", "tax", ComponentType.ENERGY, active_periods=[_ap(time(0, 0), time(0, 0))]
        )
        t = _tariff(energy_price=PriceGroup(components=[transfer, tax]))
        coll = _collection(tariff=t)
        snap = resolve_active_components(t, coll, datetime(2025, 6, 2, 12, tzinfo=UTC))
        refs = {c.reference for c in snap.active_energy_components}
        assert refs == {"main", "tax"}

    def test_fixed_component_no_recurring_always_active(self) -> None:
        fixed = PriceComponent(
            id="fee",
            reference="annual_fee",
            component_type=ComponentType.FIXED,
            description="",
            valid_period=_vp(),
            price=_price(500.0),
            recurring_periods=[],
        )
        t = _tariff(fixed_price=PriceGroup(components=[fixed]))
        coll = _collection(tariff=t)
        snap = resolve_active_components(t, coll, datetime(2025, 6, 2, 12, tzinfo=UTC))
        assert len(snap.active_fixed_components) == 1
        assert snap.active_fixed_components[0].reference == "annual_fee"

    def test_expired_component_not_active(self) -> None:
        expired = _component(
            "old",
            "old_rate",
            vp=ValidPeriod(date(2020, 1, 1), date(2021, 1, 1)),
            active_periods=[_ap(time(0, 0), time(0, 0))],
        )
        t = _tariff(power_price=PriceGroup(components=[expired]))
        coll = _collection(tariff=t)
        snap = resolve_active_components(t, coll, datetime(2025, 6, 2, 12, tzinfo=UTC))
        assert snap.active_power_components == []

    def test_duplicate_reference_warning(self) -> None:
        c1 = _component("id1", "same", active_periods=[_ap(time(0, 0), time(0, 0))])
        c2 = _component("id2", "same", active_periods=[_ap(time(0, 0), time(0, 0))])
        t = _tariff(power_price=PriceGroup(components=[c1, c2]))
        coll = _collection(tariff=t)
        snap = resolve_active_components(t, coll, datetime(2025, 6, 2, 12, tzinfo=UTC))
        assert any("same" in w for w in snap.parse_warnings)
        assert len(snap.active_power_components) == 2  # both still returned

    def test_no_active_power_component_warning(self) -> None:
        # Has power group with components, but none match right now
        comp = _component("c1", "high", active_periods=[_ap(time(7, 0), time(8, 0))])
        t = _tariff(power_price=PriceGroup(components=[comp]))
        coll = _collection(tariff=t)
        snap = resolve_active_components(t, coll, datetime(2025, 6, 2, 0, tzinfo=UTC))
        assert any("no active" in w.lower() for w in snap.parse_warnings)

    def test_empty_power_group_no_warning(self) -> None:
        # Group with zero components → no warning (nothing expected)
        t = _tariff(power_price=PriceGroup(components=[]))
        coll = _collection(tariff=t)
        snap = resolve_active_components(t, coll, datetime(2025, 6, 2, 12, tzinfo=UTC))
        assert snap.parse_warnings == []

    def test_snapshot_carries_tariff_reference(self) -> None:
        t = _tariff()
        coll = _collection(tariff=t)
        snap = resolve_active_components(t, coll, datetime(2025, 6, 2, 12, tzinfo=UTC))
        assert snap.tariff is t

    def test_snapshot_carries_at_timestamp(self) -> None:
        t = _tariff()
        coll = _collection(tariff=t)
        at = datetime(2025, 6, 2, 12, 30, tzinfo=UTC)
        snap = resolve_active_components(t, coll, at)
        assert snap.at == at

    def test_energy_component_not_active_outside_period(self) -> None:
        comp = _component(
            "e1", "energy", ComponentType.ENERGY, active_periods=[_ap(time(7, 0), time(20, 0))]
        )
        t = _tariff(energy_price=PriceGroup(components=[comp]))
        coll = _collection(tariff=t)
        snap = resolve_active_components(t, coll, datetime(2025, 6, 2, 2, tzinfo=UTC))
        assert snap.active_energy_components == []

    def test_holiday_exclusion_in_full_resolution(self) -> None:
        holiday = date(2025, 1, 6)
        wd_pat = _weekday_pat()
        hol_pat = _holiday_pat([holiday])

        high = _component(
            "high",
            "high",
            active_periods=[
                _ap(time(7, 0), time(20, 0), include=["wd"], exclude=["hol"]),
            ],
        )
        low = _component(
            "low",
            "low",
            active_periods=[
                _ap(time(0, 0), time(0, 0), include=["hol"]),
            ],
        )
        t = _tariff(power_price=PriceGroup(components=[high, low]))
        coll = TariffCollection(tariffs=[t], calendar_patterns=[wd_pat, hol_pat])

        dt = datetime(2025, 1, 6, 10, tzinfo=UTC)
        snap = resolve_active_components(t, coll, dt)
        refs = [c.reference for c in snap.active_power_components]
        assert "high" not in refs
        assert "low" in refs


# ── next_transition_at ─────────────────────────────────────────────────────────


class TestNextTransitionAt:
    def _flat(self) -> tuple[Tariff, TariffCollection]:
        comp = _component("flat", "flat", active_periods=[_ap(time(0, 0), time(0, 0))])
        t = _tariff(power_price=PriceGroup(components=[comp]))
        return t, _collection(tariff=t)

    def test_flat_tariff_no_transition_in_horizon(self) -> None:
        t, coll = self._flat()
        after = datetime(2025, 6, 2, 12, tzinfo=UTC)
        assert next_transition_at(t, coll, after, horizon=timedelta(hours=12)) is None

    def test_finds_transition_at_period_boundary(self) -> None:
        wd_pat = _weekday_pat()
        high = _component(
            "high", "high", active_periods=[_ap(time(7, 0), time(20, 0), include=["wd"])]
        )
        low = _component(
            "low",
            "low",
            active_periods=[
                _ap(time(0, 0), time(7, 0), include=["wd"]),
                _ap(time(20, 0), time(0, 0), include=["wd"]),
            ],
        )
        t = _tariff(power_price=PriceGroup(components=[high, low]))
        coll = TariffCollection(tariffs=[t], calendar_patterns=[wd_pat])

        # Monday 06:30 — currently "low", transition to "high" at 07:00
        after = datetime(2025, 1, 6, 6, 30, tzinfo=UTC)
        result = next_transition_at(t, coll, after, horizon=timedelta(hours=4))
        assert result is not None
        assert result.hour == 7
        assert result.minute == 0

    def test_scan_starts_at_next_full_minute(self) -> None:
        # After = exactly 06:30:45 → scan starts at 06:31 (not 06:30:45+1s)
        wd_pat = _weekday_pat()
        high = _component(
            "high", "high", active_periods=[_ap(time(7, 0), time(20, 0), include=["wd"])]
        )
        low = _component(
            "low",
            "low",
            active_periods=[
                _ap(time(0, 0), time(7, 0), include=["wd"]),
                _ap(time(20, 0), time(0, 0), include=["wd"]),
            ],
        )
        t = _tariff(power_price=PriceGroup(components=[high, low]))
        coll = TariffCollection(tariffs=[t], calendar_patterns=[wd_pat])

        after = datetime(2025, 1, 6, 6, 30, 45, tzinfo=UTC)
        result = next_transition_at(t, coll, after, horizon=timedelta(hours=4))
        assert result is not None
        assert result.second == 0  # whole minute boundary

    def test_returns_none_when_horizon_too_short(self) -> None:
        wd_pat = _weekday_pat()
        high = _component(
            "high", "high", active_periods=[_ap(time(7, 0), time(20, 0), include=["wd"])]
        )
        t = _tariff(power_price=PriceGroup(components=[high]))
        coll = TariffCollection(tariffs=[t], calendar_patterns=[wd_pat])

        # Already in the "high" band; next change at 20:00, but horizon only 1 hour
        after = datetime(2025, 1, 6, 10, tzinfo=UTC)
        result = next_transition_at(t, coll, after, horizon=timedelta(hours=1))
        assert result is None

    def test_transition_between_energy_components(self) -> None:
        # Energy component active only in morning
        morning = _component(
            "am",
            "morning_energy",
            ComponentType.ENERGY,
            active_periods=[_ap(time(6, 0), time(12, 0))],
        )
        afternoon = _component(
            "pm",
            "afternoon_energy",
            ComponentType.ENERGY,
            active_periods=[_ap(time(12, 0), time(20, 0))],
        )
        t = _tariff(energy_price=PriceGroup(components=[morning, afternoon]))
        coll = _collection(tariff=t)

        after = datetime(2025, 6, 2, 11, 30, tzinfo=UTC)
        result = next_transition_at(t, coll, after, horizon=timedelta(hours=2))
        assert result is not None
        assert result.hour == 12

    def test_transition_at_end_of_day_to_next_day(self) -> None:
        wd_pat = _weekday_pat()
        we_pat = _weekend_pat()
        weekday_comp = _component(
            "wd_c", "wd_band", active_periods=[_ap(time(0, 0), time(0, 0), include=["wd"])]
        )
        weekend_comp = _component(
            "we_c", "we_band", active_periods=[_ap(time(0, 0), time(0, 0), include=["we"])]
        )
        t = _tariff(power_price=PriceGroup(components=[weekday_comp, weekend_comp]))
        coll = TariffCollection(tariffs=[t], calendar_patterns=[wd_pat, we_pat])

        # Friday 23:30 — on weekday band, transition to weekend at midnight
        after = datetime(2025, 1, 10, 23, 30, tzinfo=UTC)
        result = next_transition_at(t, coll, after, horizon=timedelta(hours=2))
        assert result is not None
        assert result.date() == date(2025, 1, 11)  # Saturday
        assert result.hour == 0
        assert result.minute == 0


# ── build_day_schedule ─────────────────────────────────────────────────────────

_TZ = zoneinfo.ZoneInfo("Europe/Stockholm")


class TestBuildDaySchedule:
    def _flat_tariff(self) -> tuple[Tariff, TariffCollection]:
        comp = _component("flat", "flat", active_periods=[_ap(time(0, 0), time(0, 0))])
        t = _tariff(power_price=PriceGroup(components=[comp]))
        return t, _collection(tariff=t)

    def test_flat_tariff_produces_24_slots(self) -> None:
        t, coll = self._flat_tariff()
        slots = build_day_schedule(t, coll, date(2025, 6, 2), _TZ)
        assert len(slots) == 24

    def test_slots_are_exactly_one_hour_wide(self) -> None:
        t, coll = self._flat_tariff()
        slots = build_day_schedule(t, coll, date(2025, 6, 2), _TZ)
        for s in slots:
            assert s.end - s.start == timedelta(hours=1)

    def test_slots_start_at_midnight_and_end_at_next_midnight(self) -> None:
        t, coll = self._flat_tariff()
        slots = build_day_schedule(t, coll, date(2025, 6, 2), _TZ)
        assert slots[0].start.hour == 0
        assert slots[0].start.date() == date(2025, 6, 2)
        assert slots[-1].end.hour == 0
        assert slots[-1].end.date() == date(2025, 6, 3)

    def test_no_power_group_produces_no_slots(self) -> None:
        t = _tariff()
        coll = _collection(tariff=t)
        slots = build_day_schedule(t, coll, date(2025, 6, 2), _TZ)
        assert slots == []

    def test_slots_carry_correct_band_reference(self) -> None:
        t, coll = self._flat_tariff()
        slots = build_day_schedule(t, coll, date(2025, 6, 2), _TZ)
        assert all(s.band_reference == "flat" for s in slots)

    def test_slots_carry_price_and_currency(self) -> None:
        comp = _component(
            "c1", "band_a", price_val=2.5, active_periods=[_ap(time(0, 0), time(0, 0))]
        )
        t = _tariff(power_price=PriceGroup(components=[comp]))
        coll = _collection(tariff=t)
        slots = build_day_schedule(t, coll, date(2025, 6, 2), _TZ)
        assert all(s.price_inc_vat == 2.5 for s in slots)
        assert all(s.currency == "SEK" for s in slots)

    def test_slots_carry_ex_vat_price(self) -> None:
        comp = _component(
            "c1", "band_a", price_val=1.0, active_periods=[_ap(time(0, 0), time(0, 0))]
        )
        t = _tariff(power_price=PriceGroup(components=[comp]))
        coll = _collection(tariff=t)
        slots = build_day_schedule(t, coll, date(2025, 6, 2), _TZ)
        assert all(s.price_ex_vat == pytest.approx(0.8) for s in slots)

    def test_weekday_band_transitions(self) -> None:
        wd_pat = _weekday_pat()
        high = _component(
            "high",
            "high",
            price_val=2.0,
            active_periods=[_ap(time(7, 0), time(20, 0), include=["wd"])],
        )
        low = _component(
            "low",
            "low",
            price_val=0.5,
            active_periods=[
                _ap(time(0, 0), time(7, 0), include=["wd"]),
                _ap(time(20, 0), time(0, 0), include=["wd"]),
            ],
        )
        t = _tariff(power_price=PriceGroup(components=[high, low]))
        coll = TariffCollection(tariffs=[t], calendar_patterns=[wd_pat])

        # Monday 2025-01-06
        slots = build_day_schedule(t, coll, date(2025, 1, 6), _TZ)
        assert len(slots) == 24
        high_slots = [s for s in slots if s.band_reference == "high"]
        low_slots = [s for s in slots if s.band_reference == "low"]
        assert len(high_slots) == 13  # 07:00–20:00 = 13 hours
        assert len(low_slots) == 11  # 00:00–07:00 (7) + 20:00–24:00 (4) = 11

    def test_weekend_all_day_low_band(self) -> None:
        wd_pat = _weekday_pat()
        we_pat = _weekend_pat()
        high = _component(
            "high", "high", active_periods=[_ap(time(7, 0), time(20, 0), include=["wd"])]
        )
        low_we = _component(
            "low_we", "low_we", active_periods=[_ap(time(0, 0), time(0, 0), include=["we"])]
        )
        t = _tariff(power_price=PriceGroup(components=[high, low_we]))
        coll = TariffCollection(tariffs=[t], calendar_patterns=[wd_pat, we_pat])

        # Saturday 2025-01-11 — all slots should be "low_we"
        slots = build_day_schedule(t, coll, date(2025, 1, 11), _TZ)
        assert len(slots) == 24
        assert all(s.band_reference == "low_we" for s in slots)

    def test_holiday_band_overrides_weekday_high(self) -> None:
        holiday = date(2025, 1, 6)
        wd_pat = _weekday_pat()
        hol_pat = _holiday_pat([holiday])

        high = _component(
            "high",
            "high",
            active_periods=[
                _ap(time(7, 0), time(20, 0), include=["wd"], exclude=["hol"]),
            ],
        )
        hol_low = _component(
            "hol_low",
            "hol_low",
            active_periods=[
                _ap(time(0, 0), time(0, 0), include=["hol"]),
            ],
        )
        t = _tariff(power_price=PriceGroup(components=[high, hol_low]))
        coll = TariffCollection(tariffs=[t], calendar_patterns=[wd_pat, hol_pat])

        slots = build_day_schedule(t, coll, holiday, _TZ)
        assert all(s.band_reference == "hol_low" for s in slots)

    def test_slots_are_timezone_aware(self) -> None:
        t, coll = self._flat_tariff()
        slots = build_day_schedule(t, coll, date(2025, 6, 2), _TZ)
        for s in slots:
            assert s.start.tzinfo is not None
            assert s.end.tzinfo is not None

    def test_utc_timezone_works(self) -> None:
        t, coll = self._flat_tariff()
        slots = build_day_schedule(t, coll, date(2025, 6, 2), UTC)
        assert len(slots) == 24
        assert slots[0].start.tzinfo is UTC

    def test_consecutive_slots_are_contiguous(self) -> None:
        t, coll = self._flat_tariff()
        slots = build_day_schedule(t, coll, date(2025, 6, 2), _TZ)
        for i in range(len(slots) - 1):
            assert slots[i].end == slots[i + 1].start
