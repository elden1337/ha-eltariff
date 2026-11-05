"""Regression tests: tariffs and billing follow the tariff's local time, not UTC."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from custom_components.eltariff.api.models import (
    ActivePeriod,
    ActiveTariffSnapshot,
    CalendarPatternReferences,
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
    build_day_schedule,
    next_transition_at,
    resolve_active_components,
    resolve_current_snapshot,
)
from custom_components.eltariff.billing.cost_service import CostService
from custom_components.eltariff.billing.iso_duration import is_same_period, parse_iso_duration

TZ = ZoneInfo("Europe/Stockholm")


def _component(ref: str, *bands: tuple[time, time]) -> PriceComponent:
    no_calendar = CalendarPatternReferences(include=[], exclude=[])
    return PriceComponent(
        id=ref,
        reference=ref,
        component_type=ComponentType.PEAK,
        description=ref,
        valid_period=ValidPeriod(date(2026, 1, 1), date(2027, 1, 1)),
        price=Price(price_ex_vat=100.0, price_inc_vat=125.0, currency="SEK"),
        recurring_periods=[
            RecurringPeriod(
                active_periods=[ActivePeriod(start, end, no_calendar) for start, end in bands]
            )
        ],
    )


def _tariff(valid_from: date = date(2026, 1, 1)) -> tuple[Tariff, TariffCollection]:
    """High-load 07:00-20:00 local, low-load otherwise (Göteborg Energi's shape)."""
    tariff = MagicMock(spec=Tariff)
    tariff.valid_period = ValidPeriod(valid_from, date(2027, 1, 1))
    tariff.power_price = PriceGroup(
        components=[
            _component("high", (time(7), time(20))),
            _component("low", (time(0), time(7)), (time(20), time(0))),
        ]
    )
    tariff.energy_price = None
    tariff.fixed_price = None
    collection = MagicMock(spec=TariffCollection)
    collection.get_calendar_pattern.return_value = None
    return tariff, collection


def _snapshot() -> ActiveTariffSnapshot:
    tariff = MagicMock()
    tariff.billing_period = "P1M"
    component = replace(
        _component("high", (time(0), time(0))),
        peak_identification_settings=PeakIdentificationSettings(
            number_of_peaks_for_average=3,
            peak_function="average",
            peak_identification_period="P1D",
            peak_duration="PT1H",
        ),
    )
    return ActiveTariffSnapshot(
        at=datetime(2026, 11, 5, tzinfo=TZ),
        tariff=tariff,
        active_power_components=[component],
        active_energy_components=[],
        active_fixed_components=[],
    )


def _feed(service: CostService, snapshot: ActiveTariffSnapshot, *readings) -> None:
    for now, kwh in readings:
        service.on_energy_update(kwh, now, snapshot)


class TestScheduleBoundaries:
    @pytest.mark.parametrize(
        ("month", "day"),
        [(11, 5), (7, 1)],
        ids=["winter-utc+1", "summer-utc+2"],
    )
    @pytest.mark.parametrize(
        ("hour", "expected"),
        [(6, "low"), (7, "high"), (19, "high"), (20, "low")],
    )
    def test_band_follows_local_clock(self, month, day, hour, expected) -> None:
        tariff, collection = _tariff()
        at = datetime(2026, month, day, hour, 30, tzinfo=TZ)
        snapshot = resolve_current_snapshot(tariff, collection, at)
        assert snapshot.active_power_component.reference == expected

    def test_next_transition_is_at_local_seven(self) -> None:
        tariff, collection = _tariff()
        after = datetime(2026, 11, 5, 3, 0, tzinfo=TZ)
        assert next_transition_at(tariff, collection, after) == datetime(
            2026, 11, 5, 7, 0, tzinfo=TZ
        )

    def test_future_tariff_resolves_on_first_local_day(self) -> None:
        tariff, collection = _tariff(valid_from=date(2026, 12, 1))
        snapshot = resolve_current_snapshot(
            tariff, collection, datetime(2026, 11, 5, 12, 0, tzinfo=TZ)
        )
        assert snapshot.at == datetime(2026, 12, 1, 0, 0, tzinfo=TZ)

    def test_resolver_uses_wall_clock_of_given_datetime(self) -> None:
        """Documents why callers must not pass UTC: 07:30 local is 06:30 UTC."""
        tariff, collection = _tariff()
        utc = datetime(2026, 11, 5, 7, 30, tzinfo=TZ).astimezone(UTC)
        assert resolve_active_components(tariff, collection, utc).active_power_component.id == "low"


class TestDayScheduleOnDstDays:
    @pytest.mark.parametrize(
        ("day", "slots"),
        [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25), (date(2026, 11, 5), 24)],
        ids=["spring-forward", "fall-back", "normal"],
    )
    def test_slot_count(self, day, slots) -> None:
        tariff, collection = _tariff()
        assert len(build_day_schedule(tariff, collection, day, TZ)) == slots

    def test_slots_are_local_and_contiguous(self) -> None:
        tariff, collection = _tariff()
        slots = build_day_schedule(tariff, collection, date(2026, 10, 25), TZ)
        assert slots[0].start == datetime(2026, 10, 25, 0, 0, tzinfo=TZ)
        assert slots[-1].end == datetime(2026, 10, 26, 0, 0, tzinfo=TZ)
        assert slots[0].start.utcoffset() != slots[-1].start.utcoffset()
        assert [s.start.hour for s in slots[:5]] == [0, 1, 2, 2, 3]

    def test_band_changes_at_local_seven(self) -> None:
        tariff, collection = _tariff()
        slots = build_day_schedule(tariff, collection, date(2026, 11, 5), TZ)
        assert [s.band_reference for s in slots[6:8]] == ["low", "high"]


class TestIsSamePeriodAcrossTimezones:
    _P1D = parse_iso_duration("P1D")
    _PT1H = parse_iso_duration("PT1H")

    def test_period_is_aligned_in_first_argument_timezone(self) -> None:
        local = datetime(2026, 11, 5, 0, 30, tzinfo=TZ)
        same_local_day = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)
        previous_local_day = datetime(2026, 11, 4, 22, 0, tzinfo=UTC)
        assert is_same_period(local, same_local_day, self._P1D)
        assert not is_same_period(local, previous_local_day, self._P1D)

    def test_repeated_hour_at_dst_end_is_two_periods(self) -> None:
        first = datetime(2026, 10, 25, 2, 30, tzinfo=TZ, fold=0)
        second = datetime(2026, 10, 25, 2, 30, tzinfo=TZ, fold=1)
        assert not is_same_period(first, second, self._PT1H)
        assert is_same_period(first, second, self._P1D)


class TestCostServiceLocalCalendar:
    def _service(self) -> CostService:
        service = CostService(tz=TZ)
        service.configure_from_snapshot(_snapshot())
        return service

    def test_stored_peak_is_reported_in_local_time(self) -> None:
        service = self._service()
        snap = _snapshot()
        _feed(
            service,
            snap,
            (datetime(2026, 11, 5, 6, 5, tzinfo=UTC), 0.0),
            (datetime(2026, 11, 5, 6, 50, tzinfo=UTC), 2.0),
        )
        peak = service.get_breakdown(datetime(2026, 11, 5, 7, 0, tzinfo=UTC), snap).stored_peaks[0]
        assert peak.dt.isoformat() == "2026-11-05T07:00:00+01:00"

    def test_identification_day_starts_at_local_midnight(self) -> None:
        """23:30 and 00:30 local are different days, although both are one UTC date."""
        service = self._service()
        snap = _snapshot()
        _feed(
            service,
            snap,
            (datetime(2026, 11, 4, 22, 5, tzinfo=UTC), 0.0),  # 23:05 local
            (datetime(2026, 11, 4, 22, 50, tzinfo=UTC), 2.0),
            (datetime(2026, 11, 4, 23, 5, tzinfo=UTC), 2.0),  # 00:05 local, next day
            (datetime(2026, 11, 4, 23, 50, tzinfo=UTC), 5.0),
        )
        breakdown = service.get_breakdown(datetime(2026, 11, 5, 1, 0, tzinfo=TZ), snap)
        assert [round(p.value, 3) for p in breakdown.stored_peaks] == [2.0, 3.0]

    def test_billing_period_rolls_over_at_local_midnight(self) -> None:
        service = self._service()
        snap = _snapshot()
        _feed(
            service,
            snap,
            (datetime(2026, 11, 30, 23, 50, tzinfo=TZ), 0.0),
            # 00:10 local on the 1st is still November in UTC.
            (datetime(2026, 11, 30, 23, 10, tzinfo=UTC), 1.0),
        )
        breakdown = service.get_breakdown(datetime(2026, 11, 30, 23, 15, tzinfo=UTC), snap)
        assert breakdown.billing_period_start == datetime(2026, 12, 1, 0, 0, tzinfo=TZ)
        assert breakdown.billing_period_end == datetime(2027, 1, 1, 0, 0, tzinfo=TZ)

    def test_repeated_hour_at_dst_end_is_not_one_window(self) -> None:
        """Each 02:00 hour holds 3 kWh; merging them would report a false 6 kWh peak."""
        service = self._service()
        snap = _snapshot()
        _feed(
            service,
            snap,
            (datetime(2026, 10, 25, 0, 5, tzinfo=UTC), 0.0),  # 02:05 CEST
            (datetime(2026, 10, 25, 0, 55, tzinfo=UTC), 3.0),  # 02:55 CEST
            (datetime(2026, 10, 25, 1, 5, tzinfo=UTC), 3.0),  # 02:05 CET
            (datetime(2026, 10, 25, 1, 55, tzinfo=UTC), 6.0),  # 02:55 CET
        )
        breakdown = service.get_breakdown(datetime(2026, 10, 25, 2, 0, tzinfo=UTC), snap)
        assert breakdown.observed_peak_kwh == pytest.approx(3.0)


class TestRestoreStateSavedInUtc:
    """State saved by versions that kept everything in UTC must survive the upgrade."""

    _STATE = {
        "billing_period_start": "2026-11-01T00:00:00+00:00",
        "window_start": "2026-11-05T09:00:00+00:00",
        "window_start_reading": 10.0,
        "window_peak": 1.5,
        "prev_reading": 11.5,
        "acc_transmission": 12.0,
        "acc_tax": 3.0,
        "acc_price_curve": 0.0,
        "total_energy_kwh": 40.0,
        "peaks": [{"dt": "2026-11-04T08:00:00+00:00", "value": 4.0, "component_id": "high"}],
    }

    def _restored(self, now: datetime) -> tuple[CostService, ActiveTariffSnapshot]:
        snap = _snapshot()
        service = CostService(tz=TZ)
        assert service.restore_state(self._STATE, now=now)
        service.configure_from_snapshot(snap)
        return service, snap

    def test_current_period_is_kept_and_realigned(self) -> None:
        now = datetime(2026, 11, 5, 10, 30, tzinfo=TZ)
        service, snap = self._restored(now)
        breakdown = service.get_breakdown(now, snap)
        assert breakdown.billing_period_start == datetime(2026, 11, 1, 0, 0, tzinfo=TZ)
        assert breakdown.total_energy_kwh == pytest.approx(40.0)
        assert breakdown.stored_peaks[0].dt.isoformat() == "2026-11-04T09:00:00+01:00"

    def test_two_utc_days_in_one_local_day_keep_the_highest_peak(self) -> None:
        """23:00 UTC on Nov 4 and 08:00 UTC on Nov 5 are both Nov 5 in Stockholm."""
        peaks = [
            {"dt": "2026-11-04T23:00:00+00:00", "value": 2.0, "component_id": "high"},
            {"dt": "2026-11-05T08:00:00+00:00", "value": 5.0, "component_id": "high"},
        ]
        snap = _snapshot()
        service = CostService(tz=TZ)
        service.restore_state({**self._STATE, "peaks": peaks})
        service.configure_from_snapshot(snap)
        now = datetime(2026, 11, 5, 10, 30, tzinfo=TZ)
        assert [p.value for p in service.get_breakdown(now, snap).stored_peaks] == [5.0]

    def test_in_progress_window_continues_after_upgrade(self) -> None:
        now = datetime(2026, 11, 5, 10, 30, tzinfo=TZ)  # 09:30 UTC, same window
        service, snap = self._restored(now)
        service.on_energy_update(12.5, now, snap)
        assert service.save_state()["window_peak"] == pytest.approx(2.5)

    def test_previous_period_is_discarded(self) -> None:
        now = datetime(2026, 12, 1, 0, 30, tzinfo=TZ)
        service, snap = self._restored(now)
        assert service.get_breakdown(now, snap).total_energy_kwh == 0.0
