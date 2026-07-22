"""Unit tests for all API model dataclasses."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from custom_components.eltariff.api.models import (
    ActivePeriod,
    ActiveTariffSnapshot,
    CalendarPattern,
    CalendarPatternReferences,
    CalendarPatternType,
    ComponentType,
    PeakIdentificationSettings,
    Price,
    PriceComponent,
    PriceGroup,
    RecurringPeriod,
    ScheduleSlot,
    ServerInfo,
    Tariff,
    TariffCollection,
    ValidPeriod,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _vp(from_: str = "2025-01-01", to: str | None = "2026-01-01") -> ValidPeriod:
    return ValidPeriod(
        from_including=date.fromisoformat(from_),
        to_excluding=date.fromisoformat(to) if to else None,
    )


def _price(value: float = 1.0, currency: str = "SEK") -> Price:
    return Price(price_ex_vat=value * 0.8, price_inc_vat=value, currency=currency)


def _comp(id_: str, ref: str, ctype: ComponentType = ComponentType.PEAK) -> PriceComponent:
    return PriceComponent(
        id=id_,
        reference=ref,
        component_type=ctype,
        description="",
        valid_period=_vp(),
        price=_price(),
    )


def _tariff(id_: str = "t1", name: str = "Test", vp: ValidPeriod | None = None) -> Tariff:
    return Tariff(
        id=id_,
        name=name,
        product="P",
        company_name="AB",
        valid_period=vp or _vp(),
    )


# ── Price ──────────────────────────────────────────────────────────────────────


class TestPrice:
    def test_from_dict_basic(self) -> None:
        p = Price.from_dict({"priceExVat": 0.8, "priceIncVat": 1.0, "currency": "SEK"})
        assert p.price_ex_vat == 0.8
        assert p.price_inc_vat == 1.0
        assert p.currency == "SEK"

    def test_from_dict_zero_values(self) -> None:
        p = Price.from_dict({"priceExVat": 0.0, "priceIncVat": 0.0, "currency": "NOK"})
        assert p.price_ex_vat == 0.0
        assert p.price_inc_vat == 0.0

    def test_from_dict_coerces_string_to_float(self) -> None:
        p = Price.from_dict({"priceExVat": "1.23", "priceIncVat": "1.54", "currency": "EUR"})
        assert isinstance(p.price_ex_vat, float)
        assert isinstance(p.price_inc_vat, float)
        assert p.price_ex_vat == pytest.approx(1.23)

    def test_from_dict_different_currencies(self) -> None:
        for currency in ("SEK", "NOK", "DKK", "EUR"):
            p = Price.from_dict({"priceExVat": 1.0, "priceIncVat": 1.25, "currency": currency})
            assert p.currency == currency


# ── ValidPeriod ────────────────────────────────────────────────────────────────


class TestValidPeriod:
    def test_from_dict_with_end(self) -> None:
        vp = ValidPeriod.from_dict({"fromIncluding": "2025-01-01", "toExcluding": "2026-01-01"})
        assert vp.from_including == date(2025, 1, 1)
        assert vp.to_excluding == date(2026, 1, 1)

    def test_from_dict_open_ended(self) -> None:
        vp = ValidPeriod.from_dict({"fromIncluding": "2025-01-01"})
        assert vp.to_excluding is None

    def test_from_dict_explicit_null_end(self) -> None:
        vp = ValidPeriod.from_dict({"fromIncluding": "2025-01-01", "toExcluding": None})
        assert vp.to_excluding is None

    def test_contains_inside_range(self) -> None:
        vp = _vp()
        assert vp.contains(datetime(2025, 6, 15, 12, 0, tzinfo=UTC))

    def test_contains_before_range(self) -> None:
        vp = _vp()
        assert not vp.contains(datetime(2024, 12, 31, 23, 59, tzinfo=UTC))

    def test_contains_at_from_including_is_inclusive(self) -> None:
        vp = _vp()
        assert vp.contains(datetime(2025, 1, 1, 0, 0, tzinfo=UTC))

    def test_contains_at_to_excluding_is_exclusive(self) -> None:
        vp = _vp()
        assert not vp.contains(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))

    def test_contains_after_range(self) -> None:
        vp = _vp()
        assert not vp.contains(datetime(2027, 1, 1, 0, 0, tzinfo=UTC))

    def test_contains_open_ended_far_future(self) -> None:
        vp = ValidPeriod(from_including=date(2020, 1, 1), to_excluding=None)
        assert vp.contains(datetime(2099, 12, 31, tzinfo=UTC))

    def test_contains_open_ended_before_start(self) -> None:
        vp = ValidPeriod(from_including=date(2025, 1, 1), to_excluding=None)
        assert not vp.contains(datetime(2024, 12, 31, tzinfo=UTC))

    def test_contains_single_day_range(self) -> None:
        vp = ValidPeriod(from_including=date(2025, 6, 1), to_excluding=date(2025, 6, 2))
        assert vp.contains(datetime(2025, 6, 1, 12, 0, tzinfo=UTC))
        assert not vp.contains(datetime(2025, 6, 2, 0, 0, tzinfo=UTC))


# ── ActivePeriod ───────────────────────────────────────────────────────────────


class TestActivePeriodTimeMatches:
    def _dt(self, hour: int, minute: int = 0, second: int = 0) -> datetime:
        return datetime(2025, 6, 2, hour, minute, second, tzinfo=UTC)

    def _ap(self, start: time, end: time) -> ActivePeriod:
        return ActivePeriod(start, end, CalendarPatternReferences([], []))

    # Normal range
    def test_inside_range(self) -> None:
        assert self._ap(time(7, 0), time(20, 0)).time_matches(self._dt(9))

    def test_outside_range_before(self) -> None:
        assert not self._ap(time(7, 0), time(20, 0)).time_matches(self._dt(6, 59))

    def test_at_start_is_inclusive(self) -> None:
        assert self._ap(time(7, 0), time(20, 0)).time_matches(self._dt(7, 0))

    def test_at_end_is_exclusive(self) -> None:
        assert not self._ap(time(7, 0), time(20, 0)).time_matches(self._dt(20, 0))

    def test_outside_range_after(self) -> None:
        assert not self._ap(time(7, 0), time(20, 0)).time_matches(self._dt(21))

    # Full-day (00:00 → 00:00) convention
    def test_full_day_midnight_start(self) -> None:
        ap = self._ap(time(0, 0), time(0, 0))
        assert ap.time_matches(self._dt(0))

    def test_full_day_midday(self) -> None:
        assert self._ap(time(0, 0), time(0, 0)).time_matches(self._dt(12))

    def test_full_day_just_before_midnight(self) -> None:
        assert self._ap(time(0, 0), time(0, 0)).time_matches(self._dt(23, 59))

    # End-of-day (start → 00:00) convention means "from start through midnight"
    def test_end_of_day_at_start(self) -> None:
        assert self._ap(time(20, 0), time(0, 0)).time_matches(self._dt(20))

    def test_end_of_day_at_23_59(self) -> None:
        assert self._ap(time(20, 0), time(0, 0)).time_matches(self._dt(23, 59))

    def test_end_of_day_before_start_is_false(self) -> None:
        assert not self._ap(time(20, 0), time(0, 0)).time_matches(self._dt(19, 59))

    def test_end_of_day_midnight_is_false(self) -> None:
        # 00:00 is the start of the next day, not covered by a 20:00-00:00 band
        assert not self._ap(time(20, 0), time(0, 0)).time_matches(self._dt(0, 0))

    # Seconds/microseconds must be stripped before comparison
    def test_strips_sub_minute_precision(self) -> None:
        ap = self._ap(time(7, 0), time(20, 0))
        noisy = datetime(2025, 6, 2, 9, 30, 45, 999999, tzinfo=UTC)
        assert ap.time_matches(noisy)

    def test_exact_minute_boundary_not_affected_by_seconds(self) -> None:
        ap = self._ap(time(7, 0), time(20, 0))
        # 06:59:59 → stripped to 06:59 → still before 07:00
        assert not ap.time_matches(datetime(2025, 6, 2, 6, 59, 59, tzinfo=UTC))

    # from_dict parsing
    def test_from_dict_basic(self) -> None:
        d = {
            "fromIncluding": "07:00",
            "toExcluding": "20:00",
            "calendarPatternReferences": {"include": ["weekdays"], "exclude": ["holidays"]},
        }
        ap = ActivePeriod.from_dict(d)
        assert ap.from_including == time(7, 0)
        assert ap.to_excluding == time(20, 0)
        assert ap.calendar_pattern_references.include == ["weekdays"]
        assert ap.calendar_pattern_references.exclude == ["holidays"]

    def test_from_dict_no_refs_defaults_to_empty(self) -> None:
        ap = ActivePeriod.from_dict({"fromIncluding": "00:00", "toExcluding": "00:00"})
        assert ap.calendar_pattern_references.include == []
        assert ap.calendar_pattern_references.exclude == []

    def test_from_dict_early_morning_band(self) -> None:
        ap = ActivePeriod.from_dict({"fromIncluding": "00:00", "toExcluding": "07:00"})
        assert ap.from_including == time(0, 0)
        assert ap.to_excluding == time(7, 0)


# ── CalendarPattern ────────────────────────────────────────────────────────────


class TestCalendarPatternFromDict:
    def test_explicit_weekdays_type(self) -> None:
        p = CalendarPattern.from_dict({"id": "wd", "name": "Weekdays", "type": "weekdays"})
        assert p.pattern_type == CalendarPatternType.WEEKDAYS

    def test_explicit_weekends_type(self) -> None:
        p = CalendarPattern.from_dict({"id": "we", "name": "Weekends", "type": "weekends"})
        assert p.pattern_type == CalendarPatternType.WEEKENDS

    def test_explicit_holidays_type_with_dates(self) -> None:
        p = CalendarPattern.from_dict(
            {
                "id": "hol",
                "name": "Holidays",
                "type": "holidays",
                "dates": ["2025-01-01", "2025-06-06"],
            }
        )
        assert p.pattern_type == CalendarPatternType.HOLIDAYS
        assert date(2025, 1, 1) in p.dates
        assert date(2025, 6, 6) in p.dates
        assert len(p.dates) == 2

    def test_infer_weekdays_from_days_1_to_5(self) -> None:
        p = CalendarPattern.from_dict({"id": "wd", "name": "WD", "days": [1, 2, 3, 4, 5]})
        assert p.pattern_type == CalendarPatternType.WEEKDAYS

    def test_infer_weekdays_from_partial_days(self) -> None:
        p = CalendarPattern.from_dict({"id": "wd", "name": "WD", "days": [1, 5]})
        assert p.pattern_type == CalendarPatternType.WEEKDAYS

    def test_infer_weekends_from_days_6_7(self) -> None:
        p = CalendarPattern.from_dict({"id": "we", "name": "WE", "days": [6, 7]})
        assert p.pattern_type == CalendarPatternType.WEEKENDS

    def test_infer_weekends_wins_when_mix_contains_weekend_day(self) -> None:
        # Weekend check runs before weekday check — so a mix classifies as WEEKENDS
        p = CalendarPattern.from_dict({"id": "mix", "name": "Mix", "days": [1, 6]})
        assert p.pattern_type == CalendarPatternType.WEEKENDS

    def test_infer_holidays_when_no_days(self) -> None:
        p = CalendarPattern.from_dict({"id": "hol", "name": "Holidays"})
        assert p.pattern_type == CalendarPatternType.HOLIDAYS

    def test_infer_holidays_when_empty_days_list(self) -> None:
        p = CalendarPattern.from_dict({"id": "hol", "name": "Holidays", "days": []})
        assert p.pattern_type == CalendarPatternType.HOLIDAYS

    def test_uses_reference_key_as_id_fallback(self) -> None:
        p = CalendarPattern.from_dict({"reference": "my-ref", "name": "R", "type": "weekdays"})
        assert p.id == "my-ref"

    def test_id_takes_precedence_over_reference(self) -> None:
        p = CalendarPattern.from_dict(
            {"id": "real-id", "reference": "old-ref", "name": "R", "type": "weekdays"}
        )
        assert p.id == "real-id"

    def test_frequency_parsed(self) -> None:
        p = CalendarPattern.from_dict(
            {"id": "p", "name": "P", "type": "weekdays", "frequency": "PT15M"}
        )
        assert p.frequency == "PT15M"

    def test_no_frequency_is_none(self) -> None:
        p = CalendarPattern.from_dict({"id": "p", "name": "P", "type": "weekdays"})
        assert p.frequency is None


# ── PeakIdentificationSettings ─────────────────────────────────────────────────


class TestPeakIdentificationSettings:
    def test_from_dict_all_fields(self) -> None:
        d = {
            "numberOfPeaksForAverageCalculation": 3,
            "peakFunction": "average",
            "peakIdentificationPeriod": "P1M",
            "peakDuration": "PT1H",
        }
        s = PeakIdentificationSettings.from_dict(d)
        assert s.number_of_peaks_for_average == 3
        assert s.peak_function == "average"
        assert s.peak_identification_period == "P1M"
        assert s.peak_duration == "PT1H"

    def test_from_dict_empty_returns_all_none(self) -> None:
        s = PeakIdentificationSettings.from_dict({})
        assert s.number_of_peaks_for_average is None
        assert s.peak_function is None
        assert s.peak_identification_period is None
        assert s.peak_duration is None

    def test_from_dict_string_number_coerced_to_int(self) -> None:
        s = PeakIdentificationSettings.from_dict({"numberOfPeaksForAverageCalculation": "5"})
        assert s.number_of_peaks_for_average == 5
        assert isinstance(s.number_of_peaks_for_average, int)

    def test_from_dict_zero_peaks(self) -> None:
        s = PeakIdentificationSettings.from_dict({"numberOfPeaksForAverageCalculation": 0})
        assert s.number_of_peaks_for_average == 0


# ── ServerInfo ─────────────────────────────────────────────────────────────────


class TestServerInfo:
    def test_from_dict_with_timestamp(self) -> None:
        d = {"timezone": "Europe/Stockholm", "tariffDataLastUpdated": "2025-03-15T10:00:00+00:00"}
        info = ServerInfo.from_dict(d)
        assert info.timezone == "Europe/Stockholm"
        assert info.tariff_data_last_updated is not None
        assert info.tariff_data_last_updated.year == 2025

    def test_from_dict_without_timestamp(self) -> None:
        info = ServerInfo.from_dict({"timezone": "Europe/Oslo"})
        assert info.tariff_data_last_updated is None
        assert info.timezone == "Europe/Oslo"

    def test_from_dict_default_timezone_when_missing(self) -> None:
        info = ServerInfo.from_dict({})
        assert info.timezone == "Europe/Stockholm"

    def test_from_dict_null_timestamp(self) -> None:
        info = ServerInfo.from_dict({"tariffDataLastUpdated": None})
        assert info.tariff_data_last_updated is None

    def test_from_dict_custom_timezone(self) -> None:
        info = ServerInfo.from_dict({"timezone": "Europe/Helsinki"})
        assert info.timezone == "Europe/Helsinki"


# ── TariffCollection ───────────────────────────────────────────────────────────

_MINIMAL_TARIFF_DICT: dict = {
    "id": "t1",
    "name": "Test Tariff",
    "product": "P",
    "companyName": "Test AB",
    "validPeriod": {"fromIncluding": "2025-01-01"},
}


class TestTariffCollectionFromDict:
    def test_tariffs_list(self) -> None:
        coll = TariffCollection.from_dict(
            {"tariffs": [_MINIMAL_TARIFF_DICT], "calendarPatterns": []}
        )
        assert len(coll.tariffs) == 1
        assert coll.tariffs[0].id == "t1"

    def test_single_tariff_key(self) -> None:
        coll = TariffCollection.from_dict({"tariff": _MINIMAL_TARIFF_DICT, "calendarPatterns": []})
        assert len(coll.tariffs) == 1

    def test_missing_tariff_key_gives_empty_list(self) -> None:
        coll = TariffCollection.from_dict({"calendarPatterns": []})
        assert coll.tariffs == []

    def test_multiple_tariffs(self) -> None:
        t2 = {**_MINIMAL_TARIFF_DICT, "id": "t2"}
        coll = TariffCollection.from_dict({"tariffs": [_MINIMAL_TARIFF_DICT, t2]})
        assert len(coll.tariffs) == 2

    def test_parses_calendar_patterns(self) -> None:
        d = {
            "tariffs": [],
            "calendarPatterns": [{"id": "wd", "name": "Weekdays", "type": "weekdays"}],
        }
        coll = TariffCollection.from_dict(d)
        assert len(coll.calendar_patterns) == 1
        assert coll.calendar_patterns[0].id == "wd"

    def test_missing_calendar_patterns_key_gives_empty_list(self) -> None:
        coll = TariffCollection.from_dict({"tariffs": []})
        assert coll.calendar_patterns == []


class TestTariffCollectionLookup:
    def test_get_tariff_found(self) -> None:
        t = _tariff("t1")
        coll = TariffCollection(tariffs=[t], calendar_patterns=[])
        assert coll.get_tariff("t1") is t

    def test_get_tariff_not_found(self) -> None:
        coll = TariffCollection(tariffs=[], calendar_patterns=[])
        assert coll.get_tariff("unknown") is None

    def test_get_tariff_returns_first_match(self) -> None:
        t1 = _tariff("t1")
        t2 = _tariff("t2")
        coll = TariffCollection(tariffs=[t1, t2], calendar_patterns=[])
        assert coll.get_tariff("t2") is t2

    def test_get_calendar_pattern_found(self) -> None:
        pat = CalendarPattern(id="wd", name="Weekdays", pattern_type=CalendarPatternType.WEEKDAYS)
        coll = TariffCollection(tariffs=[], calendar_patterns=[pat])
        assert coll.get_calendar_pattern("wd") is pat

    def test_get_calendar_pattern_not_found(self) -> None:
        coll = TariffCollection(tariffs=[], calendar_patterns=[])
        assert coll.get_calendar_pattern("nope") is None


class TestFindTariffByName:
    def test_no_match_returns_none(self) -> None:
        coll = TariffCollection(tariffs=[], calendar_patterns=[])
        assert coll.find_tariff_by_name("Missing") is None

    def test_single_match(self) -> None:
        t = _tariff("t1", "Villa")
        coll = TariffCollection(tariffs=[t], calendar_patterns=[])
        assert coll.find_tariff_by_name("Villa") is t

    def test_case_sensitive_name_no_match(self) -> None:
        t = _tariff("t1", "Villa")
        coll = TariffCollection(tariffs=[t], calendar_patterns=[])
        assert coll.find_tariff_by_name("villa") is None

    def test_prefers_active_over_expired(self) -> None:
        expired = _tariff("old", "Villa", vp=ValidPeriod(date(2024, 1, 1), date(2025, 1, 1)))
        current = _tariff("new", "Villa", vp=ValidPeriod(date(2025, 1, 1), None))
        coll = TariffCollection(tariffs=[expired, current], calendar_patterns=[])
        result = coll.find_tariff_by_name("Villa", at=datetime(2025, 6, 1, 12, 0, tzinfo=UTC))
        assert result is not None
        assert result.id == "new"

    def test_returns_latest_from_including_among_multiple_active(self) -> None:
        early = _tariff("early", "Villa", vp=ValidPeriod(date(2024, 1, 1), None))
        later = _tariff("later", "Villa", vp=ValidPeriod(date(2025, 1, 1), None))
        coll = TariffCollection(tariffs=[early, later], calendar_patterns=[])
        result = coll.find_tariff_by_name("Villa", at=datetime(2025, 6, 1, 12, 0, tzinfo=UTC))
        assert result is not None
        assert result.id == "later"

    def test_falls_back_to_latest_when_none_active(self) -> None:
        old = _tariff("old", "Villa", vp=ValidPeriod(date(2022, 1, 1), date(2023, 1, 1)))
        coll = TariffCollection(tariffs=[old], calendar_patterns=[])
        # Queried in 2025 — tariff expired — should still fall back
        result = coll.find_tariff_by_name("Villa", at=datetime(2025, 1, 1, tzinfo=UTC))
        assert result is old

    def test_without_at_returns_latest_from_including(self) -> None:
        early = _tariff("early", "T", vp=ValidPeriod(date(2020, 1, 1), None))
        later = _tariff("later", "T", vp=ValidPeriod(date(2024, 1, 1), None))
        coll = TariffCollection(tariffs=[early, later], calendar_patterns=[])
        result = coll.find_tariff_by_name("T")
        assert result is not None
        assert result.id == "later"

    def test_without_at_two_identical_from_dates_returns_any(self) -> None:
        t1 = _tariff("t1", "T", vp=ValidPeriod(date(2025, 1, 1), None))
        t2 = _tariff("t2", "T", vp=ValidPeriod(date(2025, 1, 1), None))
        coll = TariffCollection(tariffs=[t1, t2], calendar_patterns=[])
        result = coll.find_tariff_by_name("T")
        assert result is not None  # doesn't crash, returns one of them


# ── ActiveTariffSnapshot ───────────────────────────────────────────────────────


class TestActiveTariffSnapshot:
    def _snap(self, power=None, energy=None, fixed=None, warnings=None) -> ActiveTariffSnapshot:
        return ActiveTariffSnapshot(
            at=datetime(2025, 6, 1, 12, 0, tzinfo=UTC),
            tariff=_tariff(),
            active_power_components=power or [],
            active_energy_components=energy or [],
            active_fixed_components=fixed or [],
            parse_warnings=warnings or [],
        )

    def test_active_power_component_empty_list_is_none(self) -> None:
        assert self._snap().active_power_component is None

    def test_active_power_component_returns_first_element(self) -> None:
        c1 = _comp("c1", "band_1")
        c2 = _comp("c2", "band_2")
        snap = self._snap(power=[c1, c2])
        assert snap.active_power_component is c1

    def test_total_energy_price_inc_vat_empty_is_zero(self) -> None:
        assert self._snap().total_energy_price_inc_vat == 0.0

    def test_total_energy_price_ex_vat_empty_is_zero(self) -> None:
        assert self._snap().total_energy_price_ex_vat == 0.0

    def test_total_energy_price_inc_vat_single_component(self) -> None:
        comp = PriceComponent(
            id="e1",
            reference="main",
            component_type=ComponentType.ENERGY,
            description="",
            valid_period=_vp(),
            price=Price(price_ex_vat=0.5, price_inc_vat=0.625, currency="SEK"),
        )
        snap = self._snap(energy=[comp])
        assert snap.total_energy_price_inc_vat == pytest.approx(0.625)

    def test_total_energy_price_sums_multiple_components(self) -> None:
        transfer = PriceComponent(
            id="main",
            reference="main",
            component_type=ComponentType.ENERGY,
            description="",
            valid_period=_vp(),
            price=Price(price_ex_vat=0.5, price_inc_vat=0.625, currency="SEK"),
        )
        tax = PriceComponent(
            id="tax",
            reference="tax",
            component_type=ComponentType.ENERGY,
            description="",
            valid_period=_vp(),
            price=Price(price_ex_vat=0.392, price_inc_vat=0.49, currency="SEK"),
        )
        snap = self._snap(energy=[transfer, tax])
        assert snap.total_energy_price_inc_vat == pytest.approx(1.115)
        assert snap.total_energy_price_ex_vat == pytest.approx(0.892)

    def test_parse_warnings_default_empty(self) -> None:
        snap = ActiveTariffSnapshot(
            at=datetime(2025, 6, 1, tzinfo=UTC),
            tariff=_tariff(),
            active_power_components=[],
            active_energy_components=[],
            active_fixed_components=[],
        )
        assert snap.parse_warnings == []

    def test_parse_warnings_propagated(self) -> None:
        snap = self._snap(warnings=["powerPrice: no active component found"])
        assert len(snap.parse_warnings) == 1


# ── ScheduleSlot ───────────────────────────────────────────────────────────────


class TestScheduleSlot:
    def test_slot_fields(self) -> None:
        import zoneinfo

        tz = zoneinfo.ZoneInfo("Europe/Stockholm")
        start = datetime(2025, 6, 2, 7, 0, tzinfo=tz)
        end = datetime(2025, 6, 2, 8, 0, tzinfo=tz)
        slot = ScheduleSlot(
            start=start,
            end=end,
            band_reference="high",
            price_inc_vat=2.5,
            price_ex_vat=2.0,
            currency="SEK",
        )
        assert slot.start == start
        assert slot.end == end
        assert slot.band_reference == "high"
        assert slot.price_inc_vat == 2.5
        assert slot.price_ex_vat == 2.0
        assert slot.currency == "SEK"


# ── Tariff.from_dict ───────────────────────────────────────────────────────────


class TestTariffFromDict:
    _BASE = {
        "id": "t1",
        "name": "Villa",
        "product": "Elnät",
        "companyName": "Göteborg Energi Nät AB",
        "validPeriod": {"fromIncluding": "2025-01-01"},
    }

    def test_minimal_fields(self) -> None:
        t = Tariff.from_dict(self._BASE)
        assert t.id == "t1"
        assert t.name == "Villa"
        assert t.product == "Elnät"
        assert t.company_name == "Göteborg Energi Nät AB"
        assert t.valid_period.from_including == date(2025, 1, 1)
        assert t.fixed_price is None
        assert t.energy_price is None
        assert t.power_price is None

    def test_optional_fields_default_none(self) -> None:
        t = Tariff.from_dict(self._BASE)
        assert t.description is None
        assert t.time_zone is None
        assert t.last_updated is None
        assert t.company_org_no is None
        assert t.direction is None
        assert t.billing_period is None

    def test_last_updated_parsed(self) -> None:
        d = {**self._BASE, "lastUpdated": "2025-03-01T08:00:00+00:00"}
        t = Tariff.from_dict(d)
        assert t.last_updated is not None
        assert t.last_updated.year == 2025

    def test_optional_string_fields(self) -> None:
        d = {
            **self._BASE,
            "description": "desc",
            "timeZone": "Europe/Stockholm",
            "companyOrgNo": "556000-0000",
            "direction": "consumption",
            "billingPeriod": "P1M",
        }
        t = Tariff.from_dict(d)
        assert t.description == "desc"
        assert t.time_zone == "Europe/Stockholm"
        assert t.billing_period == "P1M"

    def test_with_price_group(self) -> None:
        d = {
            **self._BASE,
            "fixedPrice": {
                "components": [
                    {
                        "id": "f1",
                        "reference": "annual",
                        "type": "fixed",
                        "description": "Fixed fee",
                        "validPeriod": {"fromIncluding": "2025-01-01"},
                        "price": {"priceExVat": 400.0, "priceIncVat": 500.0, "currency": "SEK"},
                    }
                ]
            },
        }
        t = Tariff.from_dict(d)
        assert t.fixed_price is not None
        assert len(t.fixed_price.components) == 1
        assert t.fixed_price.components[0].reference == "annual"


# ── CalendarPatternReferences ──────────────────────────────────────────────────


class TestCalendarPatternReferences:
    def test_from_dict_with_both_lists(self) -> None:
        refs = CalendarPatternReferences.from_dict(
            {"include": ["weekdays"], "exclude": ["holidays"]}
        )
        assert refs.include == ["weekdays"]
        assert refs.exclude == ["holidays"]

    def test_from_dict_empty_dict_defaults(self) -> None:
        refs = CalendarPatternReferences.from_dict({})
        assert refs.include == []
        assert refs.exclude == []

    def test_from_dict_only_include(self) -> None:
        refs = CalendarPatternReferences.from_dict({"include": ["weekends"]})
        assert refs.include == ["weekends"]
        assert refs.exclude == []


# ── RecurringPeriod ────────────────────────────────────────────────────────────


class TestRecurringPeriod:
    def test_from_dict_with_active_periods(self) -> None:
        d = {
            "activePeriods": [
                {"fromIncluding": "07:00", "toExcluding": "20:00"},
            ],
            "reference": "high",
            "frequency": "PT1H",
        }
        rp = RecurringPeriod.from_dict(d)
        assert len(rp.active_periods) == 1
        assert rp.active_periods[0].from_including == time(7, 0)
        assert rp.reference == "high"
        assert rp.frequency == "PT1H"

    def test_from_dict_no_active_periods(self) -> None:
        rp = RecurringPeriod.from_dict({})
        assert rp.active_periods == []
        assert rp.reference is None
        assert rp.frequency is None


# ── PriceComponent ─────────────────────────────────────────────────────────────


class TestPriceComponent:
    _BASE_DICT = {
        "id": "c1",
        "reference": "main",
        "type": "energy",
        "description": "Transfer",
        "validPeriod": {"fromIncluding": "2025-01-01"},
        "price": {"priceExVat": 0.5, "priceIncVat": 0.625, "currency": "SEK"},
    }

    def test_from_dict_null_recurring_periods_defaults_to_empty(self) -> None:
        d = {**self._BASE_DICT, "recurringPeriods": None}
        pc = PriceComponent.from_dict(d)
        assert pc.recurring_periods == []

    def test_from_dict_missing_recurring_periods_defaults_to_empty(self) -> None:
        pc = PriceComponent.from_dict(self._BASE_DICT)
        assert pc.recurring_periods == []

    def test_from_dict_null_peak_identification_settings(self) -> None:
        d = {**self._BASE_DICT, "peakIdentificationSettings": None}
        pc = PriceComponent.from_dict(d)
        assert pc.peak_identification_settings is None

    def test_from_dict_null_spot_price_settings(self) -> None:
        d = {**self._BASE_DICT, "spotPriceSettings": None}
        pc = PriceComponent.from_dict(d)
        assert pc.spot_price_settings is None

    def test_from_dict_present_spot_price_settings(self) -> None:
        d = {
            **self._BASE_DICT,
            "spotPriceSettings": {"multiplier": 1.05, "currency": "SEK"},
        }
        pc = PriceComponent.from_dict(d)
        assert pc.spot_price_settings is not None
        assert pc.spot_price_settings.multiplier == 1.05


# ── PriceGroup ─────────────────────────────────────────────────────────────────


class TestPriceGroup:
    _COMP_DICT = {
        "id": "c1",
        "reference": "main",
        "type": "energy",
        "description": "Transfer",
        "validPeriod": {"fromIncluding": "2025-01-01"},
        "price": {"priceExVat": 0.5, "priceIncVat": 0.625, "currency": "SEK"},
    }

    def test_from_dict_with_components(self) -> None:
        d = {"components": [self._COMP_DICT]}
        pg = PriceGroup.from_dict(d)
        assert len(pg.components) == 1
        assert pg.components[0].reference == "main"

    def test_from_dict_empty_components(self) -> None:
        pg = PriceGroup.from_dict({"components": []})
        assert pg.components == []

    def test_from_dict_optional_fields(self) -> None:
        pg = PriceGroup.from_dict(
            {
                "id": "pg1",
                "name": "Energy",
                "description": "desc",
                "costFunction": "sum",
                "components": [],
            }
        )
        assert pg.id == "pg1"
        assert pg.name == "Energy"
        assert pg.cost_function == "sum"

    def test_from_dict_optional_fields_default_none(self) -> None:
        pg = PriceGroup.from_dict({"components": []})
        assert pg.id is None
        assert pg.name is None
        assert pg.cost_function is None
