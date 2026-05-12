"""Unit tests for PeakTracker and CostService billing calculations."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from custom_components.eltariff.billing.iso_duration import parse_iso_duration
from custom_components.eltariff.billing.models import PeakRecord
from custom_components.eltariff.billing.peak_tracker import PeakTracker
from custom_components.eltariff.billing.cost_service import CostService


def _dt(day: int, hour: int = 12) -> datetime:
    return datetime(2025, 1, day, hour, 0, 0, tzinfo=UTC)


def _make_snapshot(annual_fixed: float = 0.0, power_price: float = 0.0) -> MagicMock:
    snap = MagicMock()
    snap.tariff.billing_period = "P1M"

    fixed_comp = MagicMock()
    fixed_comp.price.price_inc_vat = annual_fixed
    fixed_comp.price.price_ex_vat = annual_fixed / 1.25
    snap.active_fixed_components = [fixed_comp] if annual_fixed > 0 else []

    pc = MagicMock()
    pc.price.price_inc_vat = power_price
    pc.price.price_ex_vat = power_price / 1.25
    pc.peak_identification_settings = None
    snap.active_power_component = pc

    snap.active_energy_components = []
    return snap


P1D = parse_iso_duration("P1D")


class TestPeakTrackerBasics:
    def test_empty_tracker_observed_peak_is_zero(self):
        t = PeakTracker(P1D, 3)
        assert t.observed_peak == 0.0

    def test_empty_tracker_charged_peak_is_zero(self):
        t = PeakTracker(P1D, 3)
        assert t.charged_peak == 0.0

    def test_add_single_peak(self):
        t = PeakTracker(P1D, 3)
        assert t.try_add_peak(_dt(1), 5.0) is True
        assert len(t.peaks) == 1
        assert t.observed_peak == 5.0

    def test_add_peaks_under_capacity(self):
        t = PeakTracker(P1D, 3)
        t.try_add_peak(_dt(1), 5.0)
        t.try_add_peak(_dt(2), 3.0)
        assert len(t.peaks) == 2
        assert t.observed_peak == 3.0

    def test_same_period_higher_replaces(self):
        t = PeakTracker(P1D, 3)
        t.try_add_peak(_dt(1, 8), 3.0)
        result = t.try_add_peak(_dt(1, 14), 7.0)
        assert result is True
        assert len(t.peaks) == 1
        assert t.peaks[0].value == 7.0

    def test_same_period_lower_does_not_replace(self):
        t = PeakTracker(P1D, 3)
        t.try_add_peak(_dt(1, 8), 7.0)
        result = t.try_add_peak(_dt(1, 14), 3.0)
        assert result is False
        assert t.peaks[0].value == 7.0

    def test_zero_value_not_added(self):
        t = PeakTracker(P1D, 3)
        assert t.try_add_peak(_dt(1), 0.0) is False
        assert len(t.peaks) == 0


class TestPeakTrackerCapacity:
    def _tracker_with_peaks(self, values: list[float]) -> PeakTracker:
        t = PeakTracker(P1D, len(values))
        for day, v in enumerate(values, start=1):
            t.try_add_peak(_dt(day), v)
        return t

    def test_at_capacity_higher_than_min_replaces(self):
        """P1D: new peak on a new day higher than current min replaces it."""
        t = self._tracker_with_peaks([5.0, 3.0, 4.0])
        result = t.try_add_peak(_dt(4), 6.0)
        assert result is True
        assert len(t.peaks) == 3
        values = sorted(p.value for p in t.peaks)
        assert values == [4.0, 5.0, 6.0]
        assert t.observed_peak == 4.0

    def test_at_capacity_lower_than_min_not_added(self):
        """P1D: new peak lower than current min is rejected."""
        t = self._tracker_with_peaks([5.0, 3.0, 4.0])
        result = t.try_add_peak(_dt(4), 2.0)
        assert result is False
        assert t.observed_peak == 3.0

    def test_at_capacity_equal_to_min_not_added(self):
        t = self._tracker_with_peaks([5.0, 3.0, 4.0])
        result = t.try_add_peak(_dt(4), 3.0)
        assert result is False
        assert t.observed_peak == 3.0

    def test_observed_peak_is_min_of_stored(self):
        t = self._tracker_with_peaks([7.0, 2.0, 5.0])
        assert t.observed_peak == 2.0


class TestPeakTrackerChargedPeak:
    def _t(self, values: list[float], fn: str) -> PeakTracker:
        t = PeakTracker(P1D, len(values), peak_function=fn)
        for day, v in enumerate(values, start=1):
            t.try_add_peak(_dt(day), v)
        return t

    def test_average(self):
        t = self._t([4.0, 6.0, 5.0], "average")
        assert t.charged_peak == pytest.approx(5.0)

    def test_maximum(self):
        t = self._t([4.0, 6.0, 5.0], "maximum")
        assert t.charged_peak == 6.0

    def test_minimum(self):
        t = self._t([4.0, 6.0, 5.0], "minimum")
        assert t.charged_peak == 4.0

    def test_average_with_fewer_than_n_peaks(self):
        t = PeakTracker(P1D, 5, peak_function="average")
        t.try_add_peak(_dt(1), 4.0)
        t.try_add_peak(_dt(2), 6.0)
        assert t.charged_peak == pytest.approx(5.0)  # (4+6)/2, not /5


class TestCostServiceFixedCost:
    def test_fixed_cost_full_monthly_amount(self):
        """Annual 1200 SEK → 100 SEK per month, returned immediately."""
        svc = CostService()
        snap = _make_snapshot(annual_fixed=1200.0)
        svc.configure_from_snapshot(snap)
        cost = svc._compute_fixed_cost(snap)
        assert cost == pytest.approx(100.0)

    def test_fixed_cost_quarterly_billing(self):
        """P3M billing: annual 1200 SEK → 300 SEK per quarter."""
        svc = CostService()
        snap = _make_snapshot(annual_fixed=1200.0)
        snap.tariff.billing_period = "P3M"
        svc.configure_from_snapshot(snap)
        assert svc._compute_fixed_cost(snap) == pytest.approx(300.0)

    def test_fixed_cost_annual_billing(self):
        """P1Y billing: full annual cost returned in one period."""
        svc = CostService()
        snap = _make_snapshot(annual_fixed=1200.0)
        snap.tariff.billing_period = "P1Y"
        svc.configure_from_snapshot(snap)
        assert svc._compute_fixed_cost(snap) == pytest.approx(1200.0)

    def test_fixed_cost_weekly_billing(self):
        """P7D billing: annual 365.25 SEK → approx 7 SEK per week."""
        svc = CostService()
        snap = _make_snapshot(annual_fixed=365.25)
        snap.tariff.billing_period = "P7D"
        svc.configure_from_snapshot(snap)
        assert svc._compute_fixed_cost(snap) == pytest.approx(7.0)

    def test_fixed_cost_zero_when_no_fixed_components(self):
        svc = CostService()
        snap = _make_snapshot(annual_fixed=0.0)
        svc.configure_from_snapshot(snap)
        assert svc._compute_fixed_cost(snap) == 0.0


class TestCostServicePeakCost:
    def test_peak_cost_charged_peak_times_price(self):
        svc = CostService()
        snap = _make_snapshot(power_price=50.0)
        svc.configure_from_snapshot(snap)
        # Manually inject a peak
        svc._peak_tracker.try_add_peak(_dt(1), 6.0)
        cost = svc._compute_peak_cost(snap)
        assert cost == pytest.approx(300.0)  # 6.0 kWh × 50.0 SEK/kW

    def test_peak_cost_zero_when_no_peaks(self):
        svc = CostService()
        snap = _make_snapshot(power_price=50.0)
        svc.configure_from_snapshot(snap)
        assert svc._compute_peak_cost(snap) == 0.0
