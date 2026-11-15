"""EnergyPriceTotalSensor must include price-curve components (energy and power)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from custom_components.eltariff.api.models import (
    ActiveTariffSnapshot,
    ComponentType,
    Price,
    PriceComponent,
    PriceGroup,
    Tariff,
    ValidPeriod,
)
from custom_components.eltariff.const import VAT_MODE_EX, VAT_MODE_INC

AT = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
CURVE_URL = "/prices?product=spot"


def _comp(id_, ref, ctype, ex, inc, url=None) -> PriceComponent:
    return PriceComponent(
        id=id_,
        reference=ref,
        component_type=ctype,
        description="",
        valid_period=ValidPeriod(date(2025, 1, 1), date(2027, 1, 1)),
        price=Price(price_ex_vat=ex, price_inc_vat=inc, currency="SEK"),
        url=url,
    )


def _snapshot(energy, power) -> ActiveTariffSnapshot:
    tariff = Tariff(
        id="t1",
        name="T",
        product="P",
        company_name="AB",
        valid_period=ValidPeriod(date(2025, 1, 1), date(2027, 1, 1)),
        energy_price=PriceGroup(components=energy) if energy else None,
        power_price=PriceGroup(components=power) if power else None,
    )
    return ActiveTariffSnapshot(
        at=AT,
        tariff=tariff,
        active_power_components=power,
        active_energy_components=energy,
        active_fixed_components=[],
    )


def _sensor(snapshot, vat_mode):
    pytest.importorskip("homeassistant")  # sensor classes need HA installed
    from custom_components.eltariff.sensor.energy_price_total import EnergyPriceTotalSensor

    coordinator = MagicMock()
    coordinator.local_tz = ZoneInfo("Europe/Stockholm")
    coordinator.get_cached_day_schedule.return_value = []
    coordinator.data = SimpleNamespace(
        snapshot=snapshot,
        info=SimpleNamespace(tariff_data_last_updated=None),
    )
    entry = SimpleNamespace(entry_id="e1", title="x")
    return EnergyPriceTotalSensor(coordinator, entry, vat_mode)


E = ComponentType.ENERGY
P = ComponentType.DYNAMIC  # curve comps in the power group
PK = ComponentType.PEAK


class TestTotalIncludesPowerCurve:
    def test_power_curve_added_to_energy_inc_vat(self):
        snap = _snapshot(
            [_comp("e", "main", E, 0.40, 0.50)],
            [_comp("p", "spot", P, 0.80004, 1.00005, url=CURVE_URL)],
        )
        # 0.50 + 1.00005 = 1.50005 -> 1.5
        assert _sensor(snap, VAT_MODE_INC).native_value == 1.5

    def test_power_curve_added_to_energy_ex_vat(self):
        snap = _snapshot(
            [_comp("e", "main", E, 0.40, 0.50)],
            [_comp("p", "spot", P, 0.80004, 1.00005, url=CURVE_URL)],
        )
        # 0.40 + 0.80004 = 1.20004 -> 1.2
        assert _sensor(snap, VAT_MODE_EX).native_value == 1.2

    def test_static_banded_power_excluded(self):
        snap = _snapshot(
            [_comp("e", "main", E, 0.40, 0.50)],
            [_comp("p", "peak_high", PK, 40.0, 50.0)],
        )
        assert _sensor(snap, VAT_MODE_INC).native_value == 0.5
        assert _sensor(snap, VAT_MODE_EX).native_value == 0.4

    def test_only_curve_power_counted_among_mixed_power(self):
        snap = _snapshot(
            [_comp("e", "main", E, 0.40, 0.50)],
            [
                _comp("p1", "band", PK, 40.0, 50.0),
                _comp("p2", "spot", P, 0.2, 0.25, url=CURVE_URL),
            ],
        )
        assert _sensor(snap, VAT_MODE_INC).native_value == 0.75

    def test_curve_in_energy_group_counted_once(self):
        snap = _snapshot(
            [
                _comp("e", "main", E, 0.40, 0.50),
                _comp("c", "spot", E, 0.20, 0.25, url=CURVE_URL),
            ],
            [],
        )
        assert _sensor(snap, VAT_MODE_INC).native_value == 0.75

    def test_power_curve_only_no_energy(self):
        snap = _snapshot([], [_comp("p", "spot", P, 0.2, 0.25, url=CURVE_URL)])
        assert _sensor(snap, VAT_MODE_INC).native_value == 0.25

    def test_rounded_once_not_per_component(self):
        # Per-component rounding would give 0.33 + 0.33 = 0.66; once gives 0.67
        # (0.334 + 0.334 = 0.668).
        snap = _snapshot(
            [_comp("e", "main", E, 0.334, 0.334)],
            [_comp("p", "spot", P, 0.334, 0.334, url=CURVE_URL)],
        )
        assert _sensor(snap, VAT_MODE_INC).native_value == 0.67

    def test_state_has_at_most_two_decimals(self):
        snap = _snapshot(
            [_comp("e", "main", E, 0.1, 0.123456)],
            [_comp("p", "spot", P, 0.1, 0.654321, url=CURVE_URL)],
        )
        assert _sensor(snap, VAT_MODE_INC).native_value == pytest.approx(0.78, abs=1e-12)
        assert round(_sensor(snap, VAT_MODE_INC).native_value, 2) == _sensor(
            snap, VAT_MODE_INC
        ).native_value


class TestComponentsAttribute:
    def test_lists_power_curve_component(self):
        snap = _snapshot(
            [_comp("e", "main", E, 0.40, 0.50)],
            [
                _comp("p1", "band", PK, 40.0, 50.0),
                _comp("p2", "spot", P, 0.2, 0.25, url=CURVE_URL),
            ],
        )
        comps = _sensor(snap, VAT_MODE_INC).extra_state_attributes["components"]
        refs = [c["reference"] for c in comps]
        assert "main" in refs
        assert "spot" in refs
        assert "band" not in refs
        assert len(refs) == len(set(refs))
        spot = next(c for c in comps if c["reference"] == "spot")
        assert spot["price_inc_vat"] == 0.25
        assert spot["price_ex_vat"] == 0.2


class TestExistingSnapshotTotalsUnchanged:
    def test_energy_only_totals(self):
        snap = _snapshot(
            [_comp("e", "main", E, 0.40, 0.50), _comp("t", "tax", E, 0.1, 0.125)],
            [_comp("p", "spot", P, 0.2, 0.25, url=CURVE_URL)],
        )
        assert snap.total_energy_price_inc_vat == pytest.approx(0.625)
        assert snap.total_energy_price_ex_vat == pytest.approx(0.5)


class TestSnapshotTotalWithCurves:
    """Snapshot-level property (no HA needed); name is a suggestion from the spec."""

    def test_inc_vat_includes_power_curve_full_precision(self):
        snap = _snapshot(
            [_comp("e", "main", E, 0.40, 0.50)],
            [
                _comp("b", "band", PK, 40.0, 50.0),
                _comp("p", "spot", P, 0.80004, 1.00005, url=CURVE_URL),
            ],
        )
        assert snap.total_price_with_curves_inc_vat == pytest.approx(1.50005)
        assert snap.total_price_with_curves_ex_vat == pytest.approx(1.20004)

    def test_energy_curve_not_double_counted(self):
        snap = _snapshot([_comp("c", "spot", E, 0.2, 0.25, url=CURVE_URL)], [])
        assert snap.total_price_with_curves_inc_vat == pytest.approx(0.25)
