"""Advanced billing tests: PeakTracker edges, CostService full flow, VAT mode,
billing period transitions, state persistence, and billing models.

Includes time-of-use scenarios (day/night rates) and seasonal surcharge
components, since real Swedish DSO tariffs vary rates by time-band and season.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from custom_components.eltariff.billing.cost_service import CostService
from custom_components.eltariff.billing.iso_duration import parse_iso_duration
from custom_components.eltariff.billing.models import CostBreakdown, CostServiceState, PeakRecord
from custom_components.eltariff.billing.peak_tracker import PeakTracker

P1D = parse_iso_duration("P1D")
PT1H = parse_iso_duration("PT1H")
P1M = parse_iso_duration("P1M")


def _dt(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=UTC)


def _make_energy_component(
    reference: str, price_inc_vat: float, vat_ratio: float = 1.25
) -> MagicMock:
    comp = MagicMock()
    comp.reference = reference
    comp.price.price_inc_vat = price_inc_vat
    comp.price.price_ex_vat = price_inc_vat / vat_ratio
    comp.price.currency = "SEK"
    comp.url = None
    return comp


def _make_snapshot(
    annual_fixed: float = 0.0,
    power_price: float = 0.0,
    energy_components: list | None = None,
    billing_period: str = "P1M",
    vat_ratio: float = 1.25,
) -> MagicMock:
    snap = MagicMock()
    snap.tariff.billing_period = billing_period

    fixed_comp = MagicMock()
    fixed_comp.price.price_inc_vat = annual_fixed
    fixed_comp.price.price_ex_vat = annual_fixed / vat_ratio
    snap.active_fixed_components = [fixed_comp] if annual_fixed > 0 else []

    pc = MagicMock()
    pc.price.price_inc_vat = power_price
    pc.price.price_ex_vat = power_price / vat_ratio
    pc.peak_identification_settings = None
    snap.active_power_component = pc

    snap.active_energy_components = energy_components or []
    return snap


def _snap_with_rates(transmission: float = 0.0, tax: float = 0.0, **kwargs) -> MagicMock:
    comps = []
    if transmission:
        comps.append(_make_energy_component("main", transmission))
    if tax:
        comps.append(_make_energy_component("tax", tax))
    return _make_snapshot(energy_components=comps, **kwargs)


# ── PeakTracker edge cases ──────────────────────────────────────────────────────


class TestPeakTrackerReset:
    def test_reset_clears_all_peaks(self):
        t = PeakTracker(P1D, 3)
        t.try_add_peak(_dt(2025, 1, 1), 5.0)
        t.try_add_peak(_dt(2025, 1, 2), 3.0)
        t.reset()
        assert t.peaks == []
        assert t.observed_peak == 0.0
        assert t.charged_peak == 0.0

    def test_after_reset_new_peaks_accepted(self):
        t = PeakTracker(P1D, 3)
        t.try_add_peak(_dt(2025, 1, 1), 5.0)
        t.reset()
        t.try_add_peak(_dt(2025, 1, 2), 2.0)
        assert len(t.peaks) == 1
        assert t.observed_peak == 2.0


class TestPeakTrackerRestore:
    def test_restore_sets_peaks(self):
        t = PeakTracker(P1D, 3)
        records = [
            PeakRecord(dt=_dt(2025, 1, 1), value=4.0),
            PeakRecord(dt=_dt(2025, 1, 2), value=6.0),
        ]
        t.restore(records)
        assert len(t.peaks) == 2
        assert t.observed_peak == 4.0

    def test_restore_replaces_any_existing_peaks(self):
        t = PeakTracker(P1D, 3)
        t.try_add_peak(_dt(2025, 1, 1), 99.0)
        t.restore([PeakRecord(dt=_dt(2025, 1, 2), value=1.0)])
        assert len(t.peaks) == 1
        assert t.peaks[0].value == 1.0

    def test_restore_empty_list_clears_peaks(self):
        t = PeakTracker(P1D, 3)
        t.try_add_peak(_dt(2025, 1, 1), 5.0)
        t.restore([])
        assert t.peaks == []


class TestPeakTrackerSerialise:
    def test_serialise_returns_independent_copy(self):
        t = PeakTracker(P1D, 3)
        t.try_add_peak(_dt(2025, 1, 1), 5.0)
        result = t.serialise()
        result.clear()
        assert len(t.peaks) == 1

    def test_serialise_empty_tracker(self):
        assert PeakTracker(P1D, 3).serialise() == []

    def test_serialise_preserves_value_and_timestamp(self):
        dt1 = _dt(2025, 1, 1)
        t = PeakTracker(P1D, 3)
        t.try_add_peak(dt1, 7.5)
        rec = t.serialise()[0]
        assert rec.value == 7.5
        assert rec.dt == dt1


class TestPeakTrackerNumberOfPeaksClamped:
    def test_zero_peaks_clamped_to_one(self):
        t = PeakTracker(P1D, 0)
        t.try_add_peak(_dt(2025, 1, 1), 5.0)
        t.try_add_peak(_dt(2025, 1, 2), 3.0)
        assert len(t.peaks) == 1

    def test_negative_peaks_clamped_to_one(self):
        t = PeakTracker(P1D, -5)
        t.try_add_peak(_dt(2025, 1, 1), 5.0)
        assert len(t.peaks) == 1


class TestPeakTrackerMonthlyIdentificationPeriod:
    _P1M = parse_iso_duration("P1M")

    def test_two_peaks_same_month_keeps_highest(self):
        t = PeakTracker(self._P1M, 3)
        t.try_add_peak(_dt(2025, 1, 1), 3.0)
        t.try_add_peak(_dt(2025, 1, 15), 7.0)
        assert len(t.peaks) == 1
        assert t.peaks[0].value == 7.0

    def test_peaks_in_different_months_both_stored(self):
        t = PeakTracker(self._P1M, 3)
        t.try_add_peak(_dt(2025, 1, 15), 3.0)
        t.try_add_peak(_dt(2025, 2, 15), 4.0)
        assert len(t.peaks) == 2


# ── PeakRecord serialisation ────────────────────────────────────────────────────


class TestPeakRecord:
    def test_to_dict_from_dict_round_trip(self):
        dt = datetime(2025, 1, 15, 9, 0, tzinfo=UTC)
        rec = PeakRecord(dt=dt, value=6.5)
        restored = PeakRecord.from_dict(rec.to_dict())
        assert restored.value == 6.5
        assert restored.dt == dt

    def test_from_dict_coerces_string_value(self):
        rec = PeakRecord.from_dict({"dt": "2025-01-15T09:00:00+00:00", "value": "6.5"})
        assert rec.value == pytest.approx(6.5)

    def test_to_dict_has_required_keys(self):
        d = PeakRecord(dt=datetime(2025, 1, 15, tzinfo=UTC), value=1.0).to_dict()
        assert "dt" in d
        assert "value" in d


# ── CostBreakdown properties ────────────────────────────────────────────────────


class TestCostBreakdown:
    def test_total_sums_all_four_components(self):
        bd = CostBreakdown(peak_cost=100.0, transmission_cost=50.0, tax_cost=25.0, fixed_cost=75.0)
        assert bd.total == pytest.approx(250.0)

    def test_total_zero_when_all_zero(self):
        assert CostBreakdown().total == 0.0

    def test_observed_peak_kw_divides_kwh_by_duration(self):
        bd = CostBreakdown(observed_peak_kwh=5.0, peak_duration_hours=1.0)
        assert bd.observed_peak_kw == pytest.approx(5.0)

    def test_charged_peak_kw_divides_kwh_by_duration(self):
        bd = CostBreakdown(charged_peak_kwh=3.0, peak_duration_hours=0.5)
        assert bd.charged_peak_kw == pytest.approx(6.0)

    def test_peak_kw_zero_when_duration_is_zero(self):
        bd = CostBreakdown(observed_peak_kwh=5.0, peak_duration_hours=0.0)
        assert bd.observed_peak_kw == 0.0


# ── CostServiceState serialisation ─────────────────────────────────────────────


class TestCostServiceState:
    def test_full_round_trip(self):
        wdt = datetime(2025, 1, 15, 9, tzinfo=UTC)
        state = CostServiceState(
            billing_period_start_iso=datetime(2025, 1, 1, tzinfo=UTC).isoformat(),
            peaks=[PeakRecord(dt=wdt, value=4.2)],
            current_window_start_iso=wdt.isoformat(),
            current_window_start_reading=10.5,
            current_window_peak=2.1,
            prev_reading=15.0,
            accumulated_transmission_cost=8.5,
            accumulated_tax_cost=3.2,
            total_energy_kwh=100.0,
        )
        restored = CostServiceState.from_dict(state.to_dict())
        assert restored.peaks[0].value == pytest.approx(4.2)
        assert restored.accumulated_transmission_cost == pytest.approx(8.5)
        assert restored.accumulated_tax_cost == pytest.approx(3.2)
        assert restored.total_energy_kwh == pytest.approx(100.0)
        assert restored.prev_reading == pytest.approx(15.0)

    def test_from_dict_empty_dict_uses_defaults(self):
        state = CostServiceState.from_dict({})
        assert state.billing_period_start_iso is None
        assert state.peaks == []
        assert state.accumulated_transmission_cost == 0.0
        assert state.total_energy_kwh == 0.0

    def test_from_dict_ignores_non_dict_peak_entries(self):
        state = CostServiceState.from_dict({"peaks": ["not-a-dict", None, 42]})
        assert state.peaks == []


# ── CostService: basic energy accumulation ─────────────────────────────────────


class TestCostServiceEnergyAccumulation:
    def test_first_reading_sets_baseline_no_cost(self):
        svc = CostService()
        snap = _snap_with_rates(transmission=1.0)
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 8), snap)
        bd = svc.get_breakdown(_dt(2025, 1, 1, 8), snap)
        assert bd.total_energy_kwh == 0.0
        assert bd.transmission_cost == 0.0

    def test_second_reading_accumulates_delta(self):
        svc = CostService()
        snap = _snap_with_rates(transmission=1.0, tax=0.5)
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(12.0, _dt(2025, 1, 1, 9), snap)
        bd = svc.get_breakdown(_dt(2025, 1, 1, 9), snap)
        assert bd.total_energy_kwh == pytest.approx(2.0)
        assert bd.transmission_cost == pytest.approx(2.0)
        assert bd.tax_cost == pytest.approx(1.0)

    def test_multiple_readings_sum_correctly(self):
        svc = CostService()
        snap = _snap_with_rates(transmission=1.0)
        svc.configure_from_snapshot(snap)
        for reading in [0.0, 3.0, 5.0, 8.0]:
            svc.on_energy_update(reading, _dt(2025, 1, 1, 8 + int(reading)), snap)
        bd = svc.get_breakdown(_dt(2025, 1, 1, 12), snap)
        assert bd.total_energy_kwh == pytest.approx(8.0)

    def test_sensor_reset_negative_delta_skipped(self):
        svc = CostService()
        snap = _snap_with_rates(transmission=1.0)
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(100.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(200.0, _dt(2025, 1, 1, 9), snap)
        svc.on_energy_update(5.0, _dt(2025, 1, 1, 10), snap)   # reset
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 11), snap)
        bd = svc.get_breakdown(_dt(2025, 1, 1, 11), snap)
        # 100 from first delta, 0 from reset, 5 after reset
        assert bd.total_energy_kwh == pytest.approx(105.0)


# ── CostService: time-of-use (day vs night rate) ───────────────────────────────
#
# Swedish tariffs often charge more per kWh during peak hours (weekdays 6-22)
# than off-peak. The coordinator returns a different ActiveTariffSnapshot
# for each time band. CostService should apply whichever rate is current at
# the time of each energy update, producing correctly split transmission costs.


class TestCostServiceTimeOfUseRates:
    def test_day_rate_higher_than_night_accumulates_separately(self):
        svc = CostService()
        day_snap = _snap_with_rates(transmission=1.5, tax=0.5)   # peak hour rate
        night_snap = _snap_with_rates(transmission=0.5, tax=0.5)  # off-peak rate

        svc.configure_from_snapshot(day_snap)

        # 10 kWh consumed during the day (high-tariff band)
        svc.on_energy_update(0.0, _dt(2025, 1, 6, 8), day_snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 6, 9), day_snap)

        # 5 kWh consumed overnight (low-tariff band)
        svc.on_energy_update(10.0, _dt(2025, 1, 7, 0), night_snap)
        svc.on_energy_update(15.0, _dt(2025, 1, 7, 1), night_snap)

        bd = svc.get_breakdown(_dt(2025, 1, 7, 1), night_snap)
        # Transmission: 10 × 1.5 + 5 × 0.5 = 15 + 2.5 = 17.5
        assert bd.transmission_cost == pytest.approx(17.5)
        # Tax: (10 + 5) × 0.5 = 7.5
        assert bd.tax_cost == pytest.approx(7.5)
        assert bd.total_energy_kwh == pytest.approx(15.0)

    def test_three_bands_weekend_off_peak_and_holiday(self):
        """Weekday day / weekday night / weekend each have their own rate.

        The snapshot passed with each on_energy_update call is applied to the
        delta computed at that call (current - previous reading).
        """
        svc = CostService()
        weekday_peak = _snap_with_rates(transmission=2.0)
        weekday_off = _snap_with_rates(transmission=0.8)
        weekend = _snap_with_rates(transmission=0.4)

        svc.configure_from_snapshot(weekday_peak)

        svc.on_energy_update(0.0, _dt(2025, 1, 6, 8), weekday_peak)   # baseline
        svc.on_energy_update(5.0, _dt(2025, 1, 6, 10), weekday_peak)  # +5 @ 2.0 = 10.0
        svc.on_energy_update(8.0, _dt(2025, 1, 6, 22), weekday_off)   # +3 @ 0.8 = 2.4
        svc.on_energy_update(11.0, _dt(2025, 1, 11, 10), weekend)     # +3 @ 0.4 = 1.2

        bd = svc.get_breakdown(_dt(2025, 1, 11, 10), weekend)
        assert bd.transmission_cost == pytest.approx(13.6)  # 10.0 + 2.4 + 1.2

    def test_zero_cost_during_off_peak_if_rate_is_zero(self):
        svc = CostService()
        paid_snap = _snap_with_rates(transmission=1.0)
        free_snap = _snap_with_rates(transmission=0.0)

        svc.configure_from_snapshot(paid_snap)
        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), paid_snap)
        svc.on_energy_update(5.0, _dt(2025, 1, 1, 9), paid_snap)
        svc.on_energy_update(5.0, _dt(2025, 1, 1, 22), free_snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 23), free_snap)

        bd = svc.get_breakdown(_dt(2025, 1, 1, 23), free_snap)
        # Only the 5 kWh during the paid window cost anything
        assert bd.transmission_cost == pytest.approx(5.0)
        assert bd.total_energy_kwh == pytest.approx(10.0)


# ── CostService: seasonal surcharge (winter addition) ─────────────────────────
#
# Several DSOs (e.g. Göteborg Energi, Tekniska Verken) add an extra energy
# component during winter months (typically Nov–Mar). The coordinator activates
# this component in the snapshot only when the seasonal rule matches. The
# CostService must sum all active energy components per update — it must not
# hard-code a single "transmission" reference.


class TestCostServiceSeasonalSurcharge:
    def _summer_snap(self) -> MagicMock:
        """Base transfer only — no winter surcharge."""
        return _snap_with_rates(transmission=0.5, tax=0.3)

    def _winter_snap(self) -> MagicMock:
        """Base transfer + winter surcharge as extra non-tax component."""
        comps = [
            _make_energy_component("main", 0.5),
            _make_energy_component("winter", 0.4),  # seasonal add-on
            _make_energy_component("tax", 0.3),
        ]
        return _make_snapshot(energy_components=comps)

    def test_winter_snap_has_higher_effective_rate(self):
        svc = CostService()
        svc.configure_from_snapshot(self._winter_snap())
        svc.on_energy_update(0.0, _dt(2025, 1, 15, 8), self._winter_snap())
        svc.on_energy_update(10.0, _dt(2025, 1, 15, 9), self._winter_snap())
        bd = svc.get_breakdown(_dt(2025, 1, 15, 9), self._winter_snap())
        # transmission = (0.5 + 0.4) × 10 = 9.0, tax = 0.3 × 10 = 3.0
        assert bd.transmission_cost == pytest.approx(9.0)
        assert bd.tax_cost == pytest.approx(3.0)

    def test_summer_month_no_surcharge(self):
        svc = CostService()
        svc.configure_from_snapshot(self._summer_snap())
        svc.on_energy_update(0.0, _dt(2025, 7, 1, 8), self._summer_snap())
        svc.on_energy_update(10.0, _dt(2025, 7, 1, 9), self._summer_snap())
        bd = svc.get_breakdown(_dt(2025, 7, 1, 9), self._summer_snap())
        assert bd.transmission_cost == pytest.approx(5.0)  # 0.5 × 10 only

    def test_crossing_season_boundary_accumulates_correctly(self):
        """Energy in Oct (no surcharge) + energy in Nov (with surcharge)."""
        svc = CostService()
        svc.configure_from_snapshot(self._summer_snap())

        # October: summer rate, same billing period (monthly, P1M Oct)
        svc.on_energy_update(0.0, _dt(2025, 10, 31, 8), self._summer_snap())
        svc.on_energy_update(5.0, _dt(2025, 10, 31, 9), self._summer_snap())

        # November: winter rate — new billing period resets costs
        svc.on_energy_update(5.0, _dt(2025, 11, 1, 0), self._winter_snap())
        svc.on_energy_update(10.0, _dt(2025, 11, 1, 1), self._winter_snap())

        bd = svc.get_breakdown(_dt(2025, 11, 1, 1), self._winter_snap())
        # November: 5 kWh × (0.5+0.4) = 4.5 transmission, 5 kWh × 0.3 = 1.5 tax
        assert bd.transmission_cost == pytest.approx(4.5)
        assert bd.tax_cost == pytest.approx(1.5)
        assert bd.total_energy_kwh == pytest.approx(5.0)


# ── CostService: VAT mode ───────────────────────────────────────────────────────


class TestCostServiceVatMode:
    def test_inc_vat_uses_inc_vat_price(self):
        svc = CostService()
        svc.vat_mode = "inc_vat"
        snap = _snap_with_rates(transmission=1.0)
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 9), snap)
        assert svc.get_breakdown(_dt(2025, 1, 1, 9), snap).transmission_cost == pytest.approx(10.0)

    def test_ex_vat_uses_ex_vat_price(self):
        svc = CostService()
        svc.vat_mode = "ex_vat"
        snap = _snap_with_rates(transmission=1.0, vat_ratio=1.25)
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 9), snap)
        # ex_vat = 1.0 / 1.25 = 0.8, so 10 × 0.8 = 8.0
        assert svc.get_breakdown(_dt(2025, 1, 1, 9), snap).transmission_cost == pytest.approx(8.0)

    def test_inc_vat_peak_cost(self):
        svc = CostService()
        svc.vat_mode = "inc_vat"
        snap = _make_snapshot(power_price=50.0)
        svc.configure_from_snapshot(snap)
        svc._peak_tracker.try_add_peak(_dt(2025, 1, 1), 4.0)
        assert svc._compute_peak_cost(snap) == pytest.approx(200.0)

    def test_ex_vat_peak_cost(self):
        svc = CostService()
        svc.vat_mode = "ex_vat"
        snap = _make_snapshot(power_price=50.0, vat_ratio=1.25)
        svc.configure_from_snapshot(snap)
        svc._peak_tracker.try_add_peak(_dt(2025, 1, 1), 4.0)
        assert svc._compute_peak_cost(snap) == pytest.approx(160.0)  # 4 × 40

    def test_vat_mode_change_applies_to_next_update(self):
        svc = CostService()
        snap = _snap_with_rates(transmission=1.0, vat_ratio=1.25)
        svc.configure_from_snapshot(snap)

        svc.vat_mode = "inc_vat"
        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 9), snap)

        svc.vat_mode = "ex_vat"
        svc.on_energy_update(20.0, _dt(2025, 1, 1, 10), snap)

        bd = svc.get_breakdown(_dt(2025, 1, 1, 10), snap)
        # 10 kWh at 1.0 inc_vat + 10 kWh at 0.8 ex_vat
        assert bd.transmission_cost == pytest.approx(10.0 + 8.0)


# ── CostService: billing period transition ─────────────────────────────────────


class TestCostServiceBillingPeriodTransition:
    def test_new_period_resets_accumulated_energy(self):
        # prev_reading is NOT cleared on period reset, so the first reading of
        # the new period produces a delta from the last reading of the old period.
        svc = CostService()
        snap = _snap_with_rates(transmission=1.0)
        svc.configure_from_snapshot(snap)

        svc.on_energy_update(0.0, _dt(2025, 1, 15, 8), snap)
        svc.on_energy_update(50.0, _dt(2025, 1, 15, 9), snap)

        # February — new billing period; delta 50→55 = 5 kWh lands in Feb
        svc.on_energy_update(55.0, _dt(2025, 2, 1, 0), snap)

        bd = svc.get_breakdown(_dt(2025, 2, 1, 0), snap)
        assert bd.total_energy_kwh == pytest.approx(5.0)
        assert bd.transmission_cost == pytest.approx(5.0)

    def test_new_period_resets_peaks(self):
        svc = CostService()
        snap = _make_snapshot(power_price=50.0)
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 1, 15, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 15, 9), snap)
        svc.on_energy_update(10.0, _dt(2025, 2, 1, 0), snap)
        svc.on_energy_update(10.0, _dt(2025, 2, 1, 1), snap)
        bd = svc.get_breakdown(_dt(2025, 2, 1, 1), snap)
        assert bd.stored_peaks == []

    def test_billing_period_start_set_to_first_of_month(self):
        svc = CostService()
        snap = _make_snapshot()
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 3, 15, 8), snap)
        assert svc._billing_period_start == datetime(2025, 3, 1, tzinfo=UTC)

    def test_three_month_period_does_not_reset_mid_quarter(self):
        svc = CostService()
        snap = _snap_with_rates(transmission=1.0)
        snap.tariff.billing_period = "P3M"
        svc.configure_from_snapshot(snap)

        # January and February are in the same quarter (Q1)
        svc.on_energy_update(0.0, _dt(2025, 1, 15, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 15, 9), snap)
        svc.on_energy_update(10.0, _dt(2025, 2, 15, 8), snap)
        svc.on_energy_update(20.0, _dt(2025, 2, 15, 9), snap)

        bd = svc.get_breakdown(_dt(2025, 2, 15, 9), snap)
        assert bd.total_energy_kwh == pytest.approx(20.0)


# ── CostService: save / restore state ──────────────────────────────────────────


class TestCostServiceSaveRestoreState:
    def test_round_trip_preserves_all_accumulators(self):
        svc = CostService()
        snap = _snap_with_rates(transmission=1.0, tax=0.5)
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(20.0, _dt(2025, 1, 2, 9), snap)

        saved = svc.save_state()

        svc2 = CostService()
        svc2.restore_state(saved)
        svc2.configure_from_snapshot(snap)

        assert svc2._accumulated_transmission == pytest.approx(svc._accumulated_transmission)
        assert svc2._accumulated_tax == pytest.approx(svc._accumulated_tax)
        assert svc2._total_energy_kwh == pytest.approx(svc._total_energy_kwh)
        assert svc2._prev_reading == pytest.approx(svc._prev_reading)

    def test_deferred_peaks_applied_after_configure(self):
        """Peaks restored before configure_from_snapshot must not be lost."""
        svc = CostService()
        snap = _make_snapshot(power_price=50.0)
        dt1 = _dt(2025, 1, 5)
        state = CostServiceState(
            billing_period_start_iso=datetime(2025, 1, 1, tzinfo=UTC).isoformat(),
            peaks=[PeakRecord(dt=dt1, value=8.0)],
        )
        svc.restore_state(state.to_dict())
        svc.configure_from_snapshot(snap)
        assert svc._peak_tracker is not None
        assert len(svc._peak_tracker.peaks) == 1
        assert svc._peak_tracker.peaks[0].value == 8.0

    def test_save_state_billing_period_start_is_correct(self):
        svc = CostService()
        snap = _make_snapshot()
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 6, 15, 8), snap)
        saved = svc.save_state()
        assert saved["billing_period_start"] == datetime(2025, 6, 1, tzinfo=UTC).isoformat()

    def test_restore_then_continue_accumulating(self):
        """After restore, new energy updates add to restored totals, not replace them."""
        svc = CostService()
        snap = _snap_with_rates(transmission=1.0)
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 1, 10, 8), snap)
        svc.on_energy_update(30.0, _dt(2025, 1, 10, 9), snap)
        saved = svc.save_state()

        svc2 = CostService()
        svc2.restore_state(saved)
        svc2.configure_from_snapshot(snap)
        # Continue from where we left off (prev_reading = 30)
        svc2.on_energy_update(35.0, _dt(2025, 1, 10, 10), snap)
        bd = svc2.get_breakdown(_dt(2025, 1, 10, 10), snap)
        # 30 original + 5 new = 35 kWh total
        assert bd.total_energy_kwh == pytest.approx(35.0)


# ── CostService: get_breakdown output ──────────────────────────────────────────


class TestCostServiceGetBreakdown:
    def test_billing_period_end_is_first_of_next_month(self):
        svc = CostService()
        snap = _make_snapshot()
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 6, 15, 8), snap)
        bd = svc.get_breakdown(_dt(2025, 6, 15, 8), snap)
        assert bd.billing_period_end == datetime(2025, 7, 1, tzinfo=UTC)

    def test_total_equals_sum_of_parts(self):
        svc = CostService()
        snap = _make_snapshot(annual_fixed=1200.0, power_price=50.0)
        snap.active_energy_components = [
            _make_energy_component("main", 1.0),
            _make_energy_component("tax", 0.5),
        ]
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 2, 9), snap)
        svc._peak_tracker.try_add_peak(_dt(2025, 1, 2), 5.0)
        bd = svc.get_breakdown(_dt(2025, 1, 2, 9), snap)
        assert bd.total == pytest.approx(
            bd.peak_cost + bd.transmission_cost + bd.tax_cost
            + bd.fixed_cost + bd.price_curve_cost
        )

    def test_fixed_cost_1200_annual_is_100_monthly(self):
        svc = CostService()
        snap = _make_snapshot(annual_fixed=1200.0)
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        bd = svc.get_breakdown(_dt(2025, 1, 1, 8), snap)
        assert bd.fixed_cost == pytest.approx(100.0)


# ── Price-curve cost accumulation ───────────────────────────────────────────────
#
# Components with ``url`` set represent dynamic price-curve pricing (hourly grid
# tariff curves).  Their cost must accumulate separately from static
# transmission so a dedicated sensor can expose it.


def _make_price_curve_component(
    reference: str, price_inc_vat: float, url: str = "/prices/fake-uuid"
) -> MagicMock:
    """Energy component with ``url`` set — treated as price-curve."""
    comp = _make_energy_component(reference, price_inc_vat)
    comp.url = url
    return comp


class TestPriceCurveCostAccumulation:
    def test_price_curve_cost_separate_from_transmission(self):
        """Energy component with url goes into price_curve_cost, not transmission."""
        svc = CostService()
        comps = [
            _make_energy_component("main", 0.5),             # static transmission
            _make_price_curve_component("dynamic", 1.2),     # price-curve
            _make_energy_component("tax", 0.3),
        ]
        snap = _make_snapshot(energy_components=comps)
        svc.configure_from_snapshot(snap)

        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 9), snap)

        bd = svc.get_breakdown(_dt(2025, 1, 1, 9), snap)
        assert bd.transmission_cost == pytest.approx(5.0)    # 10 × 0.5
        assert bd.price_curve_cost == pytest.approx(12.0)    # 10 × 1.2
        assert bd.tax_cost == pytest.approx(3.0)             # 10 × 0.3

    def test_price_curve_only_tariff_no_static_transmission(self):
        """Tariff with only price-curve + tax, no static transmission."""
        svc = CostService()
        comps = [
            _make_price_curve_component("dynamic", 0.8),
            _make_energy_component("tax", 0.2),
        ]
        snap = _make_snapshot(energy_components=comps)
        svc.configure_from_snapshot(snap)

        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(5.0, _dt(2025, 1, 1, 9), snap)

        bd = svc.get_breakdown(_dt(2025, 1, 1, 9), snap)
        assert bd.transmission_cost == pytest.approx(0.0)
        assert bd.price_curve_cost == pytest.approx(4.0)    # 5 × 0.8
        assert bd.tax_cost == pytest.approx(1.0)

    def test_price_curve_cost_included_in_total(self):
        svc = CostService()
        comps = [
            _make_energy_component("main", 0.5),
            _make_price_curve_component("dynamic", 1.0),
            _make_energy_component("tax", 0.3),
        ]
        snap = _make_snapshot(energy_components=comps)
        svc.configure_from_snapshot(snap)

        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 9), snap)

        bd = svc.get_breakdown(_dt(2025, 1, 1, 9), snap)
        expected = (
            bd.peak_cost + bd.transmission_cost + bd.tax_cost
            + bd.fixed_cost + bd.price_curve_cost
        )
        assert bd.total == pytest.approx(expected)
        assert bd.price_curve_cost > 0

    def test_price_curve_cost_resets_on_new_billing_period(self):
        svc = CostService()
        comps = [_make_price_curve_component("dynamic", 1.0)]
        snap = _make_snapshot(energy_components=comps)
        svc.configure_from_snapshot(snap)

        svc.on_energy_update(0.0, _dt(2025, 1, 15, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 15, 9), snap)

        # New billing period — Feb
        svc.on_energy_update(15.0, _dt(2025, 2, 1, 0), snap)
        bd = svc.get_breakdown(_dt(2025, 2, 1, 0), snap)
        # Only 5 kWh delta (10→15) lands in the new period
        assert bd.price_curve_cost == pytest.approx(5.0)

    def test_varying_price_curve_rate_accumulates_correctly(self):
        """Price changes between readings (simulating hourly curve updates)."""
        svc = CostService()
        comps_high = [_make_price_curve_component("dynamic", 2.0)]
        comps_low = [_make_price_curve_component("dynamic", 0.5)]
        snap_high = _make_snapshot(energy_components=comps_high)
        snap_low = _make_snapshot(energy_components=comps_low)

        svc.configure_from_snapshot(snap_high)
        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap_high)
        svc.on_energy_update(5.0, _dt(2025, 1, 1, 9), snap_high)   # 5 × 2.0 = 10
        svc.on_energy_update(8.0, _dt(2025, 1, 1, 10), snap_low)   # 3 × 0.5 = 1.5

        bd = svc.get_breakdown(_dt(2025, 1, 1, 10), snap_low)
        assert bd.price_curve_cost == pytest.approx(11.5)

    def test_price_curve_with_ex_vat(self):
        svc = CostService()
        svc.vat_mode = "ex_vat"
        comps = [_make_price_curve_component("dynamic", 1.25)]  # inc_vat=1.25 → ex_vat=1.0
        snap = _make_snapshot(energy_components=comps)
        svc.configure_from_snapshot(snap)

        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 9), snap)

        bd = svc.get_breakdown(_dt(2025, 1, 1, 9), snap)
        assert bd.price_curve_cost == pytest.approx(10.0)  # 10 × 1.0


class TestPriceCurveCostPersistence:
    def test_save_state_includes_price_curve(self):
        svc = CostService()
        comps = [_make_price_curve_component("dynamic", 1.0)]
        snap = _make_snapshot(energy_components=comps)
        svc.configure_from_snapshot(snap)
        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 9), snap)

        saved = svc.save_state()
        assert saved["acc_price_curve"] == pytest.approx(10.0)

    def test_restore_state_restores_price_curve(self):
        svc = CostService()
        snap = _make_snapshot()
        svc.configure_from_snapshot(snap)

        saved = {
            "billing_period_start": "2025-01-01T00:00:00+00:00",
            "peaks": [],
            "acc_transmission": 5.0,
            "acc_tax": 2.0,
            "acc_price_curve": 7.5,
            "total_energy_kwh": 10.0,
        }
        svc.restore_state(saved)
        bd = svc.get_breakdown(_dt(2025, 1, 15, 8), snap)
        assert bd.price_curve_cost == pytest.approx(7.5)

    def test_restore_state_without_price_curve_defaults_to_zero(self):
        """Backward compat: old saved states won't have acc_price_curve."""
        svc = CostService()
        snap = _make_snapshot()
        svc.configure_from_snapshot(snap)

        saved = {
            "billing_period_start": "2025-01-01T00:00:00+00:00",
            "peaks": [],
            "acc_transmission": 5.0,
            "acc_tax": 2.0,
            "total_energy_kwh": 10.0,
        }
        svc.restore_state(saved)
        bd = svc.get_breakdown(_dt(2025, 1, 15, 8), snap)
        assert bd.price_curve_cost == pytest.approx(0.0)


# ── Observed peak without power component ───────────────────────────────────────
#
# When a tariff has no power_price (e.g. price-curve-only tariffs), there is
# no billed peak, but observed peak should still be tracked so users can
# monitor consumption against any contract ceiling.


class TestObservedPeakWithoutPowerComponent:
    def _no_power_snap(self, energy_rate: float = 1.0) -> MagicMock:
        """Snapshot with energy components but NO active power component."""
        comps = [_make_energy_component("main", energy_rate)]
        snap = _make_snapshot(energy_components=comps)
        snap.active_power_component = None
        return snap

    def test_observed_peak_tracked_without_power_component(self):
        svc = CostService()
        snap = self._no_power_snap()
        svc.configure_from_snapshot(snap)

        # Readings within the same 1-hour window so energy accumulates as peak
        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(2.0, datetime(2025, 1, 1, 8, 30, tzinfo=UTC), snap)
        svc.on_energy_update(5.0, datetime(2025, 1, 1, 8, 45, tzinfo=UTC), snap)
        # Next hour triggers window finalisation
        svc.on_energy_update(5.0, _dt(2025, 1, 1, 9), snap)

        bd = svc.get_breakdown(_dt(2025, 1, 1, 9), snap)
        assert bd.observed_peak_kwh > 0

    def test_peak_cost_is_zero_without_power_component(self):
        svc = CostService()
        snap = self._no_power_snap()
        svc.configure_from_snapshot(snap)

        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(10.0, _dt(2025, 1, 1, 9), snap)

        bd = svc.get_breakdown(_dt(2025, 1, 1, 9), snap)
        assert bd.peak_cost == 0.0

    def test_charged_peak_tracked_but_zero_cost_without_power(self):
        """charged_peak still has a value (for reference), but it costs nothing."""
        svc = CostService()
        snap = self._no_power_snap()
        svc.configure_from_snapshot(snap)

        svc.on_energy_update(0.0, _dt(2025, 1, 1, 8), snap)
        svc.on_energy_update(5.0, datetime(2025, 1, 1, 8, 30, tzinfo=UTC), snap)
        svc.on_energy_update(5.0, _dt(2025, 1, 1, 9), snap)

        bd = svc.get_breakdown(_dt(2025, 1, 1, 9), snap)
        assert bd.peak_cost == 0.0


# ── CostBreakdown model ────────────────────────────────────────────────────────


class TestCostBreakdownPriceCurve:
    def test_price_curve_cost_in_total(self):
        from custom_components.eltariff.billing.models import CostBreakdown

        bd = CostBreakdown(
            peak_cost=10.0,
            transmission_cost=5.0,
            tax_cost=3.0,
            fixed_cost=2.0,
            price_curve_cost=7.0,
        )
        assert bd.total == pytest.approx(27.0)

    def test_price_curve_cost_defaults_to_zero(self):
        from custom_components.eltariff.billing.models import CostBreakdown

        bd = CostBreakdown(peak_cost=10.0, transmission_cost=5.0)
        assert bd.price_curve_cost == 0.0
        assert bd.total == pytest.approx(15.0)


class TestCostServiceStatePriceCurve:
    def test_to_dict_includes_acc_price_curve(self):
        state = CostServiceState(
            accumulated_transmission_cost=5.0,
            accumulated_tax_cost=2.0,
            accumulated_price_curve_cost=3.5,
        )
        d = state.to_dict()
        assert d["acc_price_curve"] == 3.5

    def test_from_dict_parses_acc_price_curve(self):
        state = CostServiceState.from_dict({"acc_price_curve": 12.0})
        assert state.accumulated_price_curve_cost == 12.0

    def test_from_dict_missing_acc_price_curve_defaults_zero(self):
        state = CostServiceState.from_dict({})
        assert state.accumulated_price_curve_cost == 0.0
