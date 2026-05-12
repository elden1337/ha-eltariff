"""Unit tests for ISO 8601 duration parsing and period boundary utilities.

The iso_duration module has no existing test coverage. These tests document
expected behaviour of every public function.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.eltariff.billing.iso_duration import (
    ParsedDuration,
    days_in_period,
    elapsed_fraction,
    is_same_period,
    parse_iso_duration,
    period_end,
    period_start,
)


# ── parse_iso_duration ─────────────────────────────────────────────────────────


class TestParseIsoDuration:
    def test_monthly_p1m(self):
        assert parse_iso_duration("P1M") == ParsedDuration(months=1)

    def test_quarterly_p3m(self):
        assert parse_iso_duration("P3M") == ParsedDuration(months=3)

    def test_annual_p1y(self):
        assert parse_iso_duration("P1Y") == ParsedDuration(years=1)

    def test_daily_p1d(self):
        assert parse_iso_duration("P1D") == ParsedDuration(days=1)

    def test_weekly_p7d(self):
        assert parse_iso_duration("P7D") == ParsedDuration(days=7)

    def test_hourly_pt1h(self):
        assert parse_iso_duration("PT1H") == ParsedDuration(hours=1)

    def test_30_minutes(self):
        assert parse_iso_duration("PT30M") == ParsedDuration(minutes=30)

    def test_15_minutes(self):
        assert parse_iso_duration("PT15M") == ParsedDuration(minutes=15)

    def test_combined_duration(self):
        d = parse_iso_duration("P1Y2M3DT4H5M")
        assert d == ParsedDuration(years=1, months=2, days=3, hours=4, minutes=5)

    def test_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid ISO 8601"):
            parse_iso_duration("invalid")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_iso_duration("")

    def test_plain_p_returns_zero_duration(self):
        # "P" alone matches the regex with all groups None — zero duration
        assert parse_iso_duration("P") == ParsedDuration()

    def test_is_calendar_true_for_months(self):
        assert parse_iso_duration("P1M").is_calendar is True

    def test_is_calendar_true_for_years(self):
        assert parse_iso_duration("P1Y").is_calendar is True

    def test_is_calendar_false_for_days(self):
        assert parse_iso_duration("P1D").is_calendar is False

    def test_is_calendar_false_for_hours(self):
        assert parse_iso_duration("PT1H").is_calendar is False

    def test_is_calendar_false_for_minutes(self):
        assert parse_iso_duration("PT30M").is_calendar is False


# ── period_start — monthly ─────────────────────────────────────────────────────


class TestPeriodStartMonthly:
    _P1M = parse_iso_duration("P1M")

    def _dt(self, month: int, day: int, hour: int = 15) -> datetime:
        return datetime(2025, month, day, hour, 30, 45, 123456, tzinfo=UTC)

    def test_mid_month_returns_first_of_month(self):
        result = period_start(self._dt(6, 15), self._P1M)
        assert result == datetime(2025, 6, 1, 0, 0, 0, 0, tzinfo=UTC)

    def test_first_of_month_at_midnight_returns_same_day(self):
        result = period_start(self._dt(6, 1, hour=0), self._P1M)
        assert result == datetime(2025, 6, 1, 0, 0, 0, 0, tzinfo=UTC)

    def test_last_day_of_month(self):
        result = period_start(self._dt(1, 31), self._P1M)
        assert result == datetime(2025, 1, 1, 0, 0, 0, 0, tzinfo=UTC)

    def test_time_components_zeroed(self):
        dt = datetime(2025, 6, 20, 23, 59, 59, 999999, tzinfo=UTC)
        result = period_start(dt, self._P1M)
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0

    def test_january(self):
        result = period_start(self._dt(1, 15), self._P1M)
        assert result == datetime(2025, 1, 1, 0, 0, 0, 0, tzinfo=UTC)

    def test_december(self):
        result = period_start(self._dt(12, 20), self._P1M)
        assert result == datetime(2025, 12, 1, 0, 0, 0, 0, tzinfo=UTC)


# ── period_start — quarterly ───────────────────────────────────────────────────


class TestPeriodStartQuarterly:
    _P3M = parse_iso_duration("P3M")

    def _dt(self, month: int, day: int = 15) -> datetime:
        return datetime(2025, month, day, 12, 0, tzinfo=UTC)

    def test_january_is_q1(self):
        assert period_start(self._dt(1), self._P3M) == datetime(2025, 1, 1, tzinfo=UTC)

    def test_february_is_q1(self):
        assert period_start(self._dt(2), self._P3M) == datetime(2025, 1, 1, tzinfo=UTC)

    def test_march_is_q1(self):
        assert period_start(self._dt(3), self._P3M) == datetime(2025, 1, 1, tzinfo=UTC)

    def test_april_is_q2(self):
        assert period_start(self._dt(4), self._P3M) == datetime(2025, 4, 1, tzinfo=UTC)

    def test_june_is_q2(self):
        assert period_start(self._dt(6), self._P3M) == datetime(2025, 4, 1, tzinfo=UTC)

    def test_july_is_q3(self):
        assert period_start(self._dt(7), self._P3M) == datetime(2025, 7, 1, tzinfo=UTC)

    def test_october_is_q4(self):
        assert period_start(self._dt(10), self._P3M) == datetime(2025, 10, 1, tzinfo=UTC)

    def test_december_is_q4(self):
        assert period_start(self._dt(12), self._P3M) == datetime(2025, 10, 1, tzinfo=UTC)


# ── period_start — annual ──────────────────────────────────────────────────────


class TestPeriodStartAnnual:
    _P1Y = parse_iso_duration("P1Y")

    def test_mid_year_returns_jan_1(self):
        dt = datetime(2025, 6, 15, 12, 0, tzinfo=UTC)
        assert period_start(dt, self._P1Y) == datetime(2025, 1, 1, tzinfo=UTC)

    def test_jan_1_returns_jan_1(self):
        dt = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        assert period_start(dt, self._P1Y) == datetime(2025, 1, 1, tzinfo=UTC)

    def test_dec_31_returns_jan_1_same_year(self):
        dt = datetime(2025, 12, 31, 23, 59, tzinfo=UTC)
        assert period_start(dt, self._P1Y) == datetime(2025, 1, 1, tzinfo=UTC)


# ── period_start — daily ───────────────────────────────────────────────────────


class TestPeriodStartDaily:
    _P1D = parse_iso_duration("P1D")

    def test_mid_day_returns_midnight(self):
        dt = datetime(2025, 6, 15, 14, 30, 45, tzinfo=UTC)
        assert period_start(dt, self._P1D) == datetime(2025, 6, 15, 0, 0, 0, 0, tzinfo=UTC)

    def test_midnight_returns_same(self):
        dt = datetime(2025, 6, 15, 0, 0, tzinfo=UTC)
        assert period_start(dt, self._P1D) == datetime(2025, 6, 15, 0, 0, tzinfo=UTC)

    def test_one_second_before_midnight(self):
        dt = datetime(2025, 6, 15, 23, 59, 59, tzinfo=UTC)
        assert period_start(dt, self._P1D) == datetime(2025, 6, 15, 0, 0, tzinfo=UTC)


# ── period_start — hourly ──────────────────────────────────────────────────────


class TestPeriodStartHourly:
    _PT1H = parse_iso_duration("PT1H")

    def test_mid_hour_returns_top_of_hour(self):
        dt = datetime(2025, 6, 15, 9, 30, tzinfo=UTC)
        assert period_start(dt, self._PT1H) == datetime(2025, 6, 15, 9, 0, tzinfo=UTC)

    def test_on_hour_boundary_returns_same(self):
        dt = datetime(2025, 6, 15, 9, 0, tzinfo=UTC)
        assert period_start(dt, self._PT1H) == datetime(2025, 6, 15, 9, 0, tzinfo=UTC)

    def test_one_minute_before_hour(self):
        dt = datetime(2025, 6, 15, 9, 59, tzinfo=UTC)
        assert period_start(dt, self._PT1H) == datetime(2025, 6, 15, 9, 0, tzinfo=UTC)

    def test_midnight_hour(self):
        dt = datetime(2025, 6, 15, 0, 45, tzinfo=UTC)
        assert period_start(dt, self._PT1H) == datetime(2025, 6, 15, 0, 0, tzinfo=UTC)


# ── period_start — sub-hour minutes ───────────────────────────────────────────


class TestPeriodStartMinutes:
    _PT30M = parse_iso_duration("PT30M")

    def test_in_first_half_hour(self):
        dt = datetime(2025, 6, 15, 9, 15, tzinfo=UTC)
        assert period_start(dt, self._PT30M) == datetime(2025, 6, 15, 9, 0, tzinfo=UTC)

    def test_on_half_hour_boundary(self):
        dt = datetime(2025, 6, 15, 9, 30, tzinfo=UTC)
        assert period_start(dt, self._PT30M) == datetime(2025, 6, 15, 9, 30, tzinfo=UTC)

    def test_in_second_half_hour(self):
        dt = datetime(2025, 6, 15, 9, 45, tzinfo=UTC)
        assert period_start(dt, self._PT30M) == datetime(2025, 6, 15, 9, 30, tzinfo=UTC)

    def test_pt15m_quarter_boundary(self):
        PT15M = parse_iso_duration("PT15M")
        dt = datetime(2025, 6, 15, 9, 37, tzinfo=UTC)
        assert period_start(dt, PT15M) == datetime(2025, 6, 15, 9, 30, tzinfo=UTC)


# ── period_end ─────────────────────────────────────────────────────────────────


class TestPeriodEnd:
    def test_june_monthly_ends_july_1(self):
        dt = datetime(2025, 6, 15, tzinfo=UTC)
        assert period_end(dt, parse_iso_duration("P1M")) == datetime(2025, 7, 1, tzinfo=UTC)

    def test_december_monthly_ends_jan_1_next_year(self):
        dt = datetime(2025, 12, 15, tzinfo=UTC)
        assert period_end(dt, parse_iso_duration("P1M")) == datetime(2026, 1, 1, tzinfo=UTC)

    def test_annual_2025_ends_jan_1_2026(self):
        dt = datetime(2025, 6, 15, tzinfo=UTC)
        assert period_end(dt, parse_iso_duration("P1Y")) == datetime(2026, 1, 1, tzinfo=UTC)

    def test_hourly_9am_ends_10am(self):
        dt = datetime(2025, 6, 15, 9, 30, tzinfo=UTC)
        assert period_end(dt, parse_iso_duration("PT1H")) == datetime(2025, 6, 15, 10, 0, tzinfo=UTC)

    def test_q2_ends_july_1(self):
        dt = datetime(2025, 5, 15, tzinfo=UTC)
        assert period_end(dt, parse_iso_duration("P3M")) == datetime(2025, 7, 1, tzinfo=UTC)

    def test_february_non_leap_ends_mar_1(self):
        dt = datetime(2025, 2, 15, tzinfo=UTC)
        assert period_end(dt, parse_iso_duration("P1M")) == datetime(2025, 3, 1, tzinfo=UTC)

    def test_february_leap_year_ends_mar_1(self):
        dt = datetime(2024, 2, 15, tzinfo=UTC)
        assert period_end(dt, parse_iso_duration("P1M")) == datetime(2024, 3, 1, tzinfo=UTC)

    def test_daily_ends_next_day(self):
        dt = datetime(2025, 6, 15, 14, 0, tzinfo=UTC)
        assert period_end(dt, parse_iso_duration("P1D")) == datetime(2025, 6, 16, tzinfo=UTC)

    def test_30min_ends_30_min_later(self):
        dt = datetime(2025, 6, 15, 9, 15, tzinfo=UTC)
        assert period_end(dt, parse_iso_duration("PT30M")) == datetime(2025, 6, 15, 9, 30, tzinfo=UTC)

    def test_end_is_strictly_after_start(self):
        dt = datetime(2025, 6, 15, 9, 30, tzinfo=UTC)
        start = period_start(dt, parse_iso_duration("PT1H"))
        end = period_end(dt, parse_iso_duration("PT1H"))
        assert end > start


# ── is_same_period ─────────────────────────────────────────────────────────────


class TestIsSamePeriod:
    _P1M = parse_iso_duration("P1M")
    _P1D = parse_iso_duration("P1D")
    _PT1H = parse_iso_duration("PT1H")

    def test_same_month_true(self):
        d1 = datetime(2025, 6, 1, tzinfo=UTC)
        d2 = datetime(2025, 6, 30, 23, 59, tzinfo=UTC)
        assert is_same_period(d1, d2, self._P1M) is True

    def test_different_months_false(self):
        d1 = datetime(2025, 6, 30, tzinfo=UTC)
        d2 = datetime(2025, 7, 1, tzinfo=UTC)
        assert is_same_period(d1, d2, self._P1M) is False

    def test_same_day_true(self):
        d1 = datetime(2025, 6, 15, 0, 0, tzinfo=UTC)
        d2 = datetime(2025, 6, 15, 23, 59, tzinfo=UTC)
        assert is_same_period(d1, d2, self._P1D) is True

    def test_different_days_false(self):
        d1 = datetime(2025, 6, 15, 23, 59, tzinfo=UTC)
        d2 = datetime(2025, 6, 16, 0, 0, tzinfo=UTC)
        assert is_same_period(d1, d2, self._P1D) is False

    def test_same_hour_true(self):
        d1 = datetime(2025, 6, 15, 9, 0, tzinfo=UTC)
        d2 = datetime(2025, 6, 15, 9, 59, tzinfo=UTC)
        assert is_same_period(d1, d2, self._PT1H) is True

    def test_different_hours_false(self):
        d1 = datetime(2025, 6, 15, 9, 59, tzinfo=UTC)
        d2 = datetime(2025, 6, 15, 10, 0, tzinfo=UTC)
        assert is_same_period(d1, d2, self._PT1H) is False

    def test_symmetric(self):
        d1 = datetime(2025, 6, 10, tzinfo=UTC)
        d2 = datetime(2025, 6, 20, tzinfo=UTC)
        assert is_same_period(d1, d2, self._P1M) == is_same_period(d2, d1, self._P1M)

    def test_same_datetime_always_true(self):
        dt = datetime(2025, 6, 15, 9, 30, tzinfo=UTC)
        for dur_str in ("P1M", "P1D", "PT1H", "PT30M", "P1Y"):
            assert is_same_period(dt, dt, parse_iso_duration(dur_str)) is True


# ── elapsed_fraction ───────────────────────────────────────────────────────────


class TestElapsedFraction:
    def test_start_of_hour_is_zero(self):
        dt = datetime(2025, 6, 15, 9, 0, tzinfo=UTC)
        assert elapsed_fraction(dt, parse_iso_duration("PT1H")) == pytest.approx(0.0)

    def test_mid_hour_is_half(self):
        dt = datetime(2025, 6, 15, 9, 30, tzinfo=UTC)
        assert elapsed_fraction(dt, parse_iso_duration("PT1H")) == pytest.approx(0.5)

    def test_first_of_month_is_zero(self):
        dt = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)
        assert elapsed_fraction(dt, parse_iso_duration("P1M")) == pytest.approx(0.0)

    def test_result_always_between_0_and_1(self):
        dt = datetime(2025, 6, 15, 9, 30, tzinfo=UTC)
        for dur_str in ("P1M", "P1D", "PT1H", "PT30M"):
            frac = elapsed_fraction(dt, parse_iso_duration(dur_str))
            assert 0.0 <= frac <= 1.0

    def test_nearly_end_of_day_is_close_to_1(self):
        dt = datetime(2025, 6, 15, 23, 59, tzinfo=UTC)
        assert elapsed_fraction(dt, parse_iso_duration("P1D")) > 0.99

    def test_jan_1_start_of_year_is_zero(self):
        dt = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        assert elapsed_fraction(dt, parse_iso_duration("P1Y")) == pytest.approx(0.0)


# ── days_in_period ─────────────────────────────────────────────────────────────


class TestDaysInPeriod:
    def test_january_31_days(self):
        dt = datetime(2025, 1, 15, tzinfo=UTC)
        assert days_in_period(dt, parse_iso_duration("P1M")) == pytest.approx(31.0)

    def test_june_30_days(self):
        dt = datetime(2025, 6, 15, tzinfo=UTC)
        assert days_in_period(dt, parse_iso_duration("P1M")) == pytest.approx(30.0)

    def test_february_non_leap_28_days(self):
        dt = datetime(2025, 2, 15, tzinfo=UTC)
        assert days_in_period(dt, parse_iso_duration("P1M")) == pytest.approx(28.0)

    def test_february_leap_year_29_days(self):
        dt = datetime(2024, 2, 15, tzinfo=UTC)
        assert days_in_period(dt, parse_iso_duration("P1M")) == pytest.approx(29.0)

    def test_annual_non_leap_365_days(self):
        dt = datetime(2025, 6, 15, tzinfo=UTC)
        assert days_in_period(dt, parse_iso_duration("P1Y")) == pytest.approx(365.0)

    def test_annual_leap_year_366_days(self):
        dt = datetime(2024, 6, 15, tzinfo=UTC)
        assert days_in_period(dt, parse_iso_duration("P1Y")) == pytest.approx(366.0)

    def test_one_day_period(self):
        dt = datetime(2025, 6, 15, 14, 0, tzinfo=UTC)
        assert days_in_period(dt, parse_iso_duration("P1D")) == pytest.approx(1.0)

    def test_hourly_period_is_fraction_of_day(self):
        dt = datetime(2025, 6, 15, 9, 30, tzinfo=UTC)
        assert days_in_period(dt, parse_iso_duration("PT1H")) == pytest.approx(1.0 / 24.0)

    def test_q1_has_90_days(self):
        dt = datetime(2025, 2, 15, tzinfo=UTC)
        assert days_in_period(dt, parse_iso_duration("P3M")) == pytest.approx(90.0)

    def test_q2_has_91_days(self):
        dt = datetime(2025, 5, 15, tzinfo=UTC)
        assert days_in_period(dt, parse_iso_duration("P3M")) == pytest.approx(91.0)
