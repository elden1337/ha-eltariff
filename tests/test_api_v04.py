"""Compatibility with RI-SE Grid Tariff API 0.4.0."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from custom_components.eltariff.api.models import PeakIdentificationSettings, Tariff
from custom_components.eltariff.billing.cost_service import CostService


def _dt(month: int, day: int = 1, hour: int = 8) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


def _snapshot(billing: str | None, reset: str, selection: str = "P1D") -> MagicMock:
    snapshot = MagicMock()
    snapshot.tariff.billing_period = billing
    snapshot.active_power_component.id = "power"
    snapshot.active_power_component.price.price_inc_vat = 10.0
    snapshot.active_power_component.peak_identification_settings = (
        PeakIdentificationSettings.from_dict(
            {
                "peakResetPeriod": reset,
                "peakSelectionPeriod": selection,
                "peakIdentificationPeriod": "P1M",
                "peakDuration": "PT1H",
                "numberOfPeaksForAverageCalculation": 3,
                "peakFunction": "peak(main)",
            }
        )
    )
    snapshot.active_energy_components = []
    snapshot.active_fixed_components = []
    return snapshot


def _record(service: CostService, snapshot: MagicMock, when: datetime, reading: float) -> None:
    service.on_energy_update(reading, when, snapshot)
    service.on_energy_update(reading + 4, when, snapshot)


def test_v04_tariff_accepts_optional_groups_and_static_vat() -> None:
    tariff = Tariff.from_dict(
        {
            "id": "tariff",
            "validPeriod": {"fromIncluding": "2026-01-01"},
            "energyPrice": {
                "id": "energy",
                "components": [
                    {
                        "id": "component",
                        "type": "energy",
                        "validPeriod": {"fromIncluding": "2026-01-01"},
                        "price": {"priceExVat": 0.8, "currency": "SEK"},
                    }
                ],
            },
        }
    )
    assert tariff.billing_period is None
    assert tariff.fixed_price is None
    assert tariff.power_price is None
    assert tariff.energy_price.components[0].price.price_inc_vat == 1.0


def test_selection_period_takes_precedence_over_legacy_field() -> None:
    snapshot = _snapshot("P1M", "P1M")
    service = CostService()
    _record(service, snapshot, _dt(1, 2), 0)
    _record(service, snapshot, _dt(1, 3), 4)
    assert len(service.get_breakdown(_dt(1, 3), snapshot).stored_peaks) == 2


def test_monthly_selection_keeps_only_the_highest_peak() -> None:
    snapshot = _snapshot("P1M", "P1M", "P1M")
    service = CostService()
    _record(service, snapshot, _dt(1, 2), 0)
    _record(service, snapshot, _dt(1, 3), 4)
    assert [p.value for p in service.get_breakdown(_dt(1, 3), snapshot).stored_peaks] == [4]


def test_peak_reset_is_independent_of_quarterly_billing() -> None:
    snapshot = _snapshot("P3M", "P1M")
    service = CostService()
    _record(service, snapshot, _dt(1, 5), 0)
    service.on_energy_update(4, _dt(2), snapshot)
    breakdown = service.get_breakdown(_dt(2), snapshot)
    assert breakdown.stored_peaks == []
    assert breakdown.total_energy_kwh == 4
    assert breakdown.billing_period_start == _dt(1, 1, 0)


def test_peak_survives_monthly_billing_reset_until_quarterly_peak_reset() -> None:
    snapshot = _snapshot("P1M", "P3M")
    service = CostService()
    _record(service, snapshot, _dt(1, 5), 0)
    service.on_energy_update(4, _dt(2), snapshot)
    breakdown = service.get_breakdown(_dt(2), snapshot)
    assert [p.value for p in breakdown.stored_peaks] == [4]
    assert breakdown.total_energy_kwh == 0
    service.on_energy_update(4, _dt(4), snapshot)
    assert service.get_breakdown(_dt(4), snapshot).stored_peaks == []


@pytest.mark.parametrize("configure_first", [True, False])
@pytest.mark.parametrize(
    ("billing", "reset", "expected_peaks", "expected_energy"),
    [("P1M", "P3M", [4], 0), ("P3M", "P1M", [], 4)],
)
def test_restart_resets_only_expired_state(
    configure_first: bool, billing: str, reset: str, expected_peaks: list, expected_energy: int
) -> None:
    snapshot = _snapshot(billing, reset)
    original = CostService()
    _record(original, snapshot, _dt(1, 5), 0)
    saved = original.save_state()

    restored = CostService()
    if configure_first:
        restored.configure_from_snapshot(snapshot)
    restored.restore_state(saved, now=_dt(2))
    if not configure_first:
        restored.configure_from_snapshot(snapshot)
    breakdown = restored.get_breakdown(_dt(2), snapshot)
    assert [p.value for p in breakdown.stored_peaks] == expected_peaks
    assert breakdown.total_energy_kwh == expected_energy


def test_missing_billing_period_does_not_override_peak_reset() -> None:
    snapshot = _snapshot(None, "P3M")
    service = CostService()
    _record(service, snapshot, _dt(1, 5), 0)
    service.on_energy_update(4, _dt(2), snapshot)
    assert [p.value for p in service.get_breakdown(_dt(2), snapshot).stored_peaks] == [4]


@pytest.mark.parametrize(("unit", "expected"), [("kW", 160), ("kWh", 40)])
def test_peak_cost_uses_average_power_for_kw(unit: str, expected: int) -> None:
    snapshot = _snapshot("P1M", "P1M")
    snapshot.active_power_component.unit = unit
    snapshot.active_power_component.peak_identification_settings = (
        PeakIdentificationSettings.from_dict(
            {
                "peakResetPeriod": "P1M",
                "peakSelectionPeriod": "P1D",
                "peakDuration": "PT15M",
                "numberOfPeaksForAverageCalculation": 1,
            }
        )
    )
    service = CostService()
    _record(service, snapshot, _dt(1, 5), 0)
    assert service.get_breakdown(_dt(1, 5), snapshot).peak_cost == expected
