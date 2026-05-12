"""Tests for schedule resolution logic."""

from datetime import date, datetime, time, timezone

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
from custom_components.eltariff.api.schedule import resolve_active_components


def _make_price(value: float = 1.0, currency: str = "SEK") -> Price:
    return Price(price_ex_vat=value * 0.8, price_inc_vat=value, currency=currency)


def _make_valid_period(
    from_: date = date(2025, 1, 1),
    to: date = date(2026, 1, 1),
) -> ValidPeriod:
    return ValidPeriod(from_including=from_, to_excluding=to)


def _make_active_period(
    from_t: time,
    to_t: time,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> ActivePeriod:
    return ActivePeriod(
        from_including=from_t,
        to_excluding=to_t,
        calendar_pattern_references=CalendarPatternReferences(
            include=include or [],
            exclude=exclude or [],
        ),
    )


def _weekday_pattern(id_: str = "weekdays") -> CalendarPattern:
    return CalendarPattern(id=id_, name="Weekdays", pattern_type=CalendarPatternType.WEEKDAYS)


def _weekend_pattern(id_: str = "weekends") -> CalendarPattern:
    return CalendarPattern(id=id_, name="Weekends", pattern_type=CalendarPatternType.WEEKENDS)


def _holiday_pattern(dates: list[date], id_: str = "holidays") -> CalendarPattern:
    return CalendarPattern(
        id=id_, name="Holidays", pattern_type=CalendarPatternType.HOLIDAYS, dates=dates
    )


def _make_power_component(
    id_: str,
    reference: str,
    active_periods: list[ActivePeriod],
    price: float = 1.0,
) -> PriceComponent:
    return PriceComponent(
        id=id_,
        reference=reference,
        component_type=ComponentType.PEAK,
        description="",
        valid_period=_make_valid_period(),
        price=_make_price(price),
        recurring_periods=[RecurringPeriod(active_periods=active_periods)],
        peak_identification_settings=PeakIdentificationSettings(3),
    )


def _make_collection(patterns: list[CalendarPattern], tariff: Tariff) -> TariffCollection:
    return TariffCollection(tariffs=[tariff], calendar_patterns=patterns)


class TestWeekdayHighLow:
    """Göteborg-style 07-20 high / rest low on weekdays, all-day low on weekends."""

    def setup_method(self) -> None:
        weekday_pat = _weekday_pattern()
        weekend_pat = _weekend_pattern()

        high = _make_power_component(
            "high",
            "winter_high",
            [
                _make_active_period(
                    time(7, 0),
                    time(20, 0),
                    include=["weekdays"],
                    exclude=["holidays"],
                )
            ],
            price=2.0,
        )
        low_weekday = _make_power_component(
            "low_wd",
            "winter_low_weekday",
            [
                _make_active_period(
                    time(0, 0), time(7, 0), include=["weekdays"], exclude=["holidays"]
                ),
                _make_active_period(
                    time(20, 0), time(0, 0), include=["weekdays"], exclude=["holidays"]
                ),
            ],
            price=0.5,
        )
        low_weekend = _make_power_component(
            "low_we",
            "winter_low_weekend",
            [_make_active_period(time(0, 0), time(0, 0), include=["weekends"])],
            price=0.5,
        )

        tariff = Tariff(
            id="t1",
            name="Test",
            product="P1",
            company_name="Test AB",
            valid_period=_make_valid_period(),
            power_price=PriceGroup(components=[high, low_weekday, low_weekend]),
        )
        self.collection = _make_collection([weekday_pat, weekend_pat], tariff)
        self.tariff = tariff

    def _resolve(self, dt: datetime) -> list[str]:
        snap = resolve_active_components(self.tariff, self.collection, dt)
        return [c.reference for c in snap.active_power_components]

    def test_weekday_morning_rush(self) -> None:
        dt = datetime(2025, 1, 6, 9, 0, tzinfo=timezone.utc)  # Monday 09:00
        assert self._resolve(dt) == ["winter_high"]

    def test_weekday_night(self) -> None:
        dt = datetime(2025, 1, 6, 2, 0, tzinfo=timezone.utc)  # Monday 02:00
        assert self._resolve(dt) == ["winter_low_weekday"]

    def test_weekday_evening_after_peak(self) -> None:
        dt = datetime(2025, 1, 6, 21, 0, tzinfo=timezone.utc)  # Monday 21:00
        assert self._resolve(dt) == ["winter_low_weekday"]

    def test_weekend_all_day(self) -> None:
        dt = datetime(2025, 1, 4, 14, 0, tzinfo=timezone.utc)  # Saturday 14:00
        assert self._resolve(dt) == ["winter_low_weekend"]

    def test_exactly_at_band_start(self) -> None:
        dt = datetime(2025, 1, 6, 7, 0, tzinfo=timezone.utc)  # Monday 07:00 sharp
        assert self._resolve(dt) == ["winter_high"]

    def test_exactly_at_band_end_exclusive(self) -> None:
        dt = datetime(2025, 1, 6, 20, 0, tzinfo=timezone.utc)  # Monday 20:00 = outside high
        assert self._resolve(dt) == ["winter_low_weekday"]


class TestHolidayExclusion:
    def test_holiday_excluded_from_weekday_high(self) -> None:
        holiday = date(2025, 1, 6)  # Trettondag jul, a Monday
        weekday_pat = _weekday_pattern()
        holiday_pat = _holiday_pattern([holiday])

        high = _make_power_component(
            "high",
            "high",
            [
                _make_active_period(
                    time(7, 0), time(20, 0), include=["weekdays"], exclude=["holidays"]
                )
            ],
        )
        low = _make_power_component(
            "low",
            "low",
            [_make_active_period(time(0, 0), time(0, 0), include=["holidays"])],
        )

        tariff = Tariff(
            id="t1",
            name="T",
            product="P",
            company_name="X",
            valid_period=_make_valid_period(),
            power_price=PriceGroup(components=[high, low]),
        )
        collection = _make_collection([weekday_pat, holiday_pat], tariff)

        dt = datetime(2025, 1, 6, 10, 0, tzinfo=timezone.utc)
        snap = resolve_active_components(tariff, collection, dt)
        refs = [c.reference for c in snap.active_power_components]
        assert "high" not in refs
        assert "low" in refs
