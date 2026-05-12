"""Provocative TDD tests: peaks must be attributed to the price band they
were recorded in.

User scenario that motivated these tests
----------------------------------------
A Swedish DSO tariff charges 135 kr/kW for the daytime power component but
0 kr/kW for nights and weekends.  Both bands are realised as *two distinct
PriceComponents* on the same tariff; only one is "active" at a time.

Two weeks into the billing period:

* Monday 12:00 (daytime, 135 kr/kW active):
    observed/charged peak must reflect ONLY peaks measured while the paid
    band was active.  peak_cost = charged_paid_peak * 135.

* Monday 22:00 (evening, 0 kr/kW active):
    There is no chargeable peak right now — peak_cost MUST be 0.  The
    observed peak surfaced by the sensor MUST NOT silently keep showing the
    midday number as if it were currently being billed (automations rely on
    this signal).  It must reflect the currently-active band (which has no
    chargeable peak at 22:00 ⇒ 0).

The current implementation stores every hourly peak in a single global
PeakTracker without remembering which band was active when it was recorded.
A free-band spike therefore pollutes the charged peak for the paid band.

These tests are intentionally provocative and are expected to fail until
peaks are attributed per power-component.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.eltariff.billing.cost_service import CostService

# ── Helpers ─────────────────────────────────────────────────────────────────


def _dt(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=UTC)


def _power_component(comp_id: str, price_inc_vat: float) -> MagicMock:
    """A power PriceComponent with a stable identity so band attribution
    can be implemented in the future."""
    pc = MagicMock()
    pc.id = comp_id
    pc.reference = "power"
    pc.price.price_inc_vat = price_inc_vat
    pc.price.price_ex_vat = price_inc_vat / 1.25
    pc.price.currency = "SEK"
    pc.peak_identification_settings = None
    return pc


_DAY_BAND = _power_component("power-day", 135.0)
_FREE_BAND = _power_component("power-free", 0.0)


def _snap(active_band: MagicMock, billing_period: str = "P1M") -> MagicMock:
    """Build an ActiveTariffSnapshot stub with one active power component."""
    snap = MagicMock()
    snap.tariff.billing_period = billing_period
    snap.active_fixed_components = []
    snap.active_energy_components = []
    snap.active_power_components = [active_band]
    snap.active_power_component = active_band
    return snap


def _is_day_band(now: datetime) -> bool:
    """Mon–Fri, 06:00–22:00 local-naive."""
    if now.weekday() >= 5:  # Sat/Sun
        return False
    return 6 <= now.hour < 22


def _band_for(now: datetime) -> MagicMock:
    return _DAY_BAND if _is_day_band(now) else _FREE_BAND


def _feed_hourly(
    service: CostService,
    start: datetime,
    hours: int,
    profile,
) -> float:
    """Drive the service hour-by-hour.

    ``profile(hour_start)`` returns kWh consumed during the hour starting at
    ``hour_start``.  The energy is distributed across six 10-minute ticks
    inside the hour so the PT1H peak window can register the load (the
    service's window logic does not credit a spike that arrives on the
    transition tick — see notes in the file).

    Returns the final cumulative reading.
    """
    reading = 0.0
    seed_t = start - timedelta(minutes=5)
    service.on_energy_update(reading, seed_t, _snap(_band_for(seed_t)))
    for h in range(hours):
        hour_start = start + timedelta(hours=h)
        # Boundary tick (delta=0) so the new window's start_reading captures
        # the cumulative value BEFORE this hour's spike.
        service.on_energy_update(reading, hour_start, _snap(_band_for(hour_start)))
        kwh = profile(hour_start)
        per_tick = kwh / 6.0
        for minute in (5, 15, 25, 35, 45, 55):
            t = hour_start + timedelta(minutes=minute)
            reading += per_tick
            service.on_energy_update(reading, t, _snap(_band_for(t)))
    # Flush the final window by ticking just past the simulated range.
    final_t = start + timedelta(hours=hours)
    service.on_energy_update(reading, final_t, _snap(_band_for(final_t)))
    return reading


# ── Tests ───────────────────────────────────────────────────────────────────


class TestPeaksAttributedToBand:
    """Peaks recorded while the free (0 kr/kW) band was active must not
    contribute to the charged peak that gets multiplied by the paid rate."""

    def test_night_only_consumption_yields_zero_peak_cost_at_midday(self):
        """User runs a heavy load only at 03:00 every night for two weeks
        (free band).  Walking into Monday midday, peak_cost MUST be 0 because
        no peak was ever recorded during the paid band."""
        service = CostService()
        start = _dt(2026, 5, 1, 0)  # Friday 00:00

        def night_load(t: datetime) -> float:
            # 10 kWh blast at 03:00 local each night, otherwise idle.
            return 10.0 if t.hour == 3 else 0.0

        _feed_hourly(service, start, hours=24 * 14, profile=night_load)

        monday_midday = _dt(2026, 5, 11, 12)  # Monday wk2, 12:00, day band
        snap_day = _snap(_DAY_BAND)
        service.on_energy_update(
            service._prev_reading or 0.0, monday_midday, snap_day
        )

        breakdown = service.get_breakdown(monday_midday, snap_day)

        assert breakdown.peak_cost == pytest.approx(0.0), (
            f"Night-only peaks must not be billable at the day rate, "
            f"but peak_cost={breakdown.peak_cost}"
        )

    def test_weekend_peak_does_not_drive_monday_midday_cost(self):
        """A single big Saturday 14:00 spike must not be charged at 135 kr/kW
        on Monday."""
        service = CostService()
        start = _dt(2026, 5, 2, 0)  # Saturday 00:00 (free)

        def sat_spike(t: datetime) -> float:
            return 8.0 if (t.weekday() == 5 and t.hour == 14) else 0.0

        _feed_hourly(service, start, hours=24 * 3, profile=sat_spike)

        monday_midday = _dt(2026, 5, 4, 12)
        snap_day = _snap(_DAY_BAND)
        service.on_energy_update(
            service._prev_reading or 0.0, monday_midday, snap_day
        )
        breakdown = service.get_breakdown(monday_midday, snap_day)

        assert breakdown.peak_cost == pytest.approx(0.0), (
            "Weekend peaks must not be billed at the weekday rate"
        )

    def test_daytime_peak_charged_correctly_at_midday(self):
        """Sanity check: a single 4 kWh weekday-noon peak must yield
        4 * 135 = 540 kr at the active day band."""
        service = CostService()
        start = _dt(2026, 5, 4, 0)  # Monday

        def noon_load(t: datetime) -> float:
            return 4.0 if (t.weekday() < 5 and t.hour == 12) else 0.0

        _feed_hourly(service, start, hours=15, profile=noon_load)

        when = _dt(2026, 5, 4, 13)
        snap = _snap(_DAY_BAND)
        service.on_energy_update(service._prev_reading or 0.0, when, snap)
        breakdown = service.get_breakdown(when, snap)

        assert breakdown.peak_cost == pytest.approx(4.0 * 135.0), (
            f"Expected 4 kWh * 135 = 540, got {breakdown.peak_cost}"
        )

    def test_free_band_spike_does_not_inflate_charged_peak_when_max_function(self):
        """With peak_function='maximum' and ONE peak slot, a 12 kWh free-band
        spike must NOT become the charged_peak that the 135 kr/kW rate is
        applied to."""
        service = CostService()
        # Force max-function, single-peak configuration.
        snap_cfg = _snap(_DAY_BAND)
        snap_cfg.active_power_component.peak_identification_settings = MagicMock(
            peak_identification_period="P1D",
            peak_duration="PT1H",
            number_of_peaks_for_average=1,
            peak_function="maximum",
        )
        service.configure_from_snapshot(snap_cfg)

        # Day band peak: 3 kWh on Monday 10:00
        # Free band peak: 12 kWh Monday 03:00 (should NOT count)
        start = _dt(2026, 5, 4, 0)

        def mixed(t: datetime) -> float:
            if t.hour == 3:
                return 12.0
            if t.hour == 10:
                return 3.0
            return 0.0

        _feed_hourly(service, start, hours=12, profile=mixed)

        when = _dt(2026, 5, 4, 12)
        snap = _snap(_DAY_BAND)
        snap.active_power_component.peak_identification_settings = (
            snap_cfg.active_power_component.peak_identification_settings
        )
        service.on_energy_update(service._prev_reading or 0.0, when, snap)
        breakdown = service.get_breakdown(when, snap)

        # Cost must reflect ONLY the 3 kWh day peak, not the 12 kWh free spike.
        assert breakdown.peak_cost == pytest.approx(3.0 * 135.0), (
            f"Free-band 12 kWh spike leaked into charged_peak: "
            f"peak_cost={breakdown.peak_cost} (expected 405)"
        )
        assert breakdown.charged_peak_kwh == pytest.approx(3.0), (
            f"charged_peak_kwh polluted by free-band peak: "
            f"{breakdown.charged_peak_kwh} (expected 3.0)"
        )


class TestObservedPeakReflectsActiveBand:
    """The sensor value MUST swing with the currently-active band, because
    automations key off of it.  A user reading the sensor at midday should
    see the day-band peak; at 22:00 (free) the same sensor should report no
    chargeable peak."""

    def test_observed_peak_visible_at_midday_disappears_in_evening(self):
        service = CostService()
        start = _dt(2026, 5, 4, 0)  # Monday

        # 5 kWh peak at Monday 12:00 (day band).
        def profile(t: datetime) -> float:
            return 5.0 if t.hour == 12 else 0.0

        _feed_hourly(service, start, hours=15, profile=profile)

        # Midday reading: paid band active.
        midday = _dt(2026, 5, 4, 13)
        snap_day = _snap(_DAY_BAND)
        service.on_energy_update(service._prev_reading or 0.0, midday, snap_day)
        b_day = service.get_breakdown(midday, snap_day)

        assert b_day.observed_peak_kwh == pytest.approx(5.0), (
            f"Expected paid-band observed peak of 5.0 at midday, "
            f"got {b_day.observed_peak_kwh}"
        )
        assert b_day.peak_cost == pytest.approx(5.0 * 135.0)

        # Evening reading: free band active.  Same physical peak, but no
        # chargeable peak under the active band.
        evening = _dt(2026, 5, 4, 22)
        snap_free = _snap(_FREE_BAND)
        service.on_energy_update(service._prev_reading or 0.0, evening, snap_free)
        b_eve = service.get_breakdown(evening, snap_free)

        assert b_eve.peak_cost == pytest.approx(0.0), (
            f"Evening free-band peak_cost must be 0, got {b_eve.peak_cost}"
        )
        assert b_eve.observed_peak_kwh != b_day.observed_peak_kwh, (
            "observed_peak_kwh must differ between paid and free bands — "
            "automations rely on a band-relevant signal, not a global max."
        )

    def test_observed_peak_at_free_time_is_zero_when_no_free_band_peaks(self):
        """If no peaks have ever been recorded during the free band, then at
        an evening read-out observed_peak for *the active band* must be 0."""
        service = CostService()
        start = _dt(2026, 5, 4, 0)

        def daytime_only(t: datetime) -> float:
            return 6.0 if (t.weekday() < 5 and t.hour == 11) else 0.0

        _feed_hourly(service, start, hours=14, profile=daytime_only)

        evening = _dt(2026, 5, 4, 22)
        snap_free = _snap(_FREE_BAND)
        service.on_energy_update(service._prev_reading or 0.0, evening, snap_free)
        b = service.get_breakdown(evening, snap_free)

        assert b.observed_peak_kwh == pytest.approx(0.0), (
            f"Expected 0 observed peak under the free band, got "
            f"{b.observed_peak_kwh} (likely leaking the day-band peak)"
        )


class TestRunningMonthBandIntegrity:
    """Two weeks into a billing period, with realistic mixed traffic, the
    charged peak must be the average (or max) of *paid-band* daily peaks
    only."""

    def test_two_weeks_mixed_yields_paid_band_charged_peak(self):
        service = CostService()
        start = _dt(2026, 5, 1, 0)  # Friday

        # Profile:
        #   * Every weekday at 10:00 → 2.0 kWh (paid)
        #   * Every weekday at 14:00 → 3.0 kWh (paid)  ← daily max under paid
        #   * Every night 02:00      → 9.0 kWh (free)  ← biggest of the day
        #   * Saturdays 13:00        → 7.0 kWh (free)
        def profile(t: datetime) -> float:
            if t.hour == 2:
                return 9.0
            if t.weekday() < 5 and t.hour == 10:
                return 2.0
            if t.weekday() < 5 and t.hour == 14:
                return 3.0
            if t.weekday() == 5 and t.hour == 13:
                return 7.0
            return 0.0

        _feed_hourly(service, start, hours=24 * 14, profile=profile)

        when = _dt(2026, 5, 15, 12)  # Friday wk3, midday — paid band
        snap = _snap(_DAY_BAND)
        service.on_energy_update(service._prev_reading or 0.0, when, snap)
        b = service.get_breakdown(when, snap)

        # Default peak_function='average', number_of_peaks=1 → single peak.
        # Paid-band daily max is 3.0 kWh; charged_peak must equal 3.0.
        assert b.charged_peak_kwh == pytest.approx(3.0), (
            f"After two weeks, charged_peak_kwh should be the paid-band "
            f"daily peak (3.0), got {b.charged_peak_kwh}"
        )
        assert b.peak_cost == pytest.approx(3.0 * 135.0), (
            f"peak_cost should be 3.0 * 135 = 405, got {b.peak_cost}"
        )

    def test_evening_readback_reports_zero_cost_after_full_paid_history(self):
        """Same history; queried at 22:00 it must report 0 peak_cost."""
        service = CostService()
        start = _dt(2026, 5, 1, 0)

        def profile(t: datetime) -> float:
            if t.weekday() < 5 and t.hour == 14:
                return 3.0
            return 0.0

        _feed_hourly(service, start, hours=24 * 14, profile=profile)

        when = _dt(2026, 5, 15, 22)  # evening, free band
        snap = _snap(_FREE_BAND)
        service.on_energy_update(service._prev_reading or 0.0, when, snap)
        b = service.get_breakdown(when, snap)

        assert b.peak_cost == pytest.approx(0.0)
