"""Power-group price-curve components ("timpris") are billed per consumed kWh,
never as a peak. Uses real snapshots/components (not MagicMock)."""

from __future__ import annotations

from datetime import UTC, date, datetime

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
from custom_components.eltariff.billing.cost_service import CostService

CURVE_URL = "/prices?product=timpris"
VP = ValidPeriod(date(2024, 1, 1), date(2027, 1, 1))


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2025, 1, day, hour, minute, tzinfo=UTC)


def _comp(id_, ref, ctype, ex, inc, url=None, currency="SEK") -> PriceComponent:
    return PriceComponent(
        id=id_,
        reference=ref,
        component_type=ctype,
        description="",
        valid_period=VP,
        price=Price(price_ex_vat=ex, price_inc_vat=inc, currency=currency),
        url=url,
        unit="kW" if ctype != ComponentType.ENERGY else None,
    )


def _curve(id_="curve", ex=0.8, inc=1.0, currency="SEK") -> PriceComponent:
    return _comp(id_, "hourly", ComponentType.DYNAMIC, ex, inc, url=CURVE_URL, currency=currency)


def _peak(id_="peak", ex=40.0, inc=50.0) -> PriceComponent:
    return _comp(id_, "peak", ComponentType.PEAK, ex, inc)


def _energy(id_, ref, ex, inc, url=None) -> PriceComponent:
    return _comp(id_, ref, ComponentType.ENERGY, ex, inc, url=url)


def _snap(power=(), energy=()) -> ActiveTariffSnapshot:
    power, energy = list(power), list(energy)
    tariff = Tariff(
        id="t",
        name="T",
        product="P",
        company_name="AB",
        valid_period=VP,
        billing_period="P1M",
        energy_price=PriceGroup(components=energy) if energy else None,
        power_price=PriceGroup(components=power) if power else None,
    )
    return ActiveTariffSnapshot(
        at=_dt(1, 8),
        tariff=tariff,
        active_power_components=power,
        active_energy_components=energy,
        active_fixed_components=[],
    )


def _run(snap, vat_mode="inc_vat", kwh=10.0):
    svc = CostService()
    svc.vat_mode = vat_mode
    svc.configure_from_snapshot(snap)
    svc.on_energy_update(0.0, _dt(1, 8), snap)
    svc.on_energy_update(kwh, _dt(1, 8, 30), snap)
    return svc, svc.get_breakdown(_dt(1, 8, 30), snap)


class TestPowerCurveEnergyBilling:
    def test_inc_vat_accumulates_in_price_curve_cost(self):
        _, bd = _run(_snap(power=[_curve()]))
        assert bd.price_curve_cost == pytest.approx(10.0)  # 10 kWh * 1.0

    def test_ex_vat(self):
        _, bd = _run(_snap(power=[_curve()]), vat_mode="ex_vat")
        assert bd.price_curve_cost == pytest.approx(8.0)  # 10 kWh * 0.8

    def test_flows_into_total(self):
        _, bd = _run(_snap(power=[_curve()]))
        assert bd.total == pytest.approx(10.0)

    def test_added_to_energy_group_curve(self):
        snap = _snap(
            power=[_curve("p", 0.8, 1.0)],
            energy=[_energy("c", "spot", 0.2, 0.25, url="/prices?x")],
        )
        _, bd = _run(snap)
        assert bd.price_curve_cost == pytest.approx(12.5)  # 10 * (1.0 + 0.25)

    def test_same_id_in_both_groups_counted_once(self):
        shared = _comp("same", "spot", ComponentType.DYNAMIC, 0.8, 1.0, url=CURVE_URL)
        _, bd = _run(_snap(power=[shared], energy=[shared]))
        assert bd.price_curve_cost == pytest.approx(10.0)

    def test_varying_hourly_rate(self):
        svc = CostService()
        s1, s2 = _snap(power=[_curve(inc=2.0)]), _snap(power=[_curve(inc=0.5)])
        svc.configure_from_snapshot(s1)
        svc.on_energy_update(0.0, _dt(1, 8), s1)
        svc.on_energy_update(5.0, _dt(1, 9), s1)  # 5 * 2.0
        svc.on_energy_update(8.0, _dt(1, 10), s2)  # 3 * 0.5
        assert svc.get_breakdown(_dt(1, 10), s2).price_curve_cost == pytest.approx(11.5)

    def test_persisted_in_save_state(self):
        svc, _ = _run(_snap(power=[_curve()]))
        assert svc.save_state()["acc_price_curve"] == pytest.approx(10.0)


class TestPowerCurveNotAPeak:
    def test_curve_only_has_no_peak_cost(self):
        _, bd = _run(_snap(power=[_curve()]))
        assert bd.peak_cost == 0.0

    def test_curve_only_peak_fields_match_tariff_without_peak_component(self):
        _, bd = _run(_snap(power=[_curve()]))
        _, base = _run(_snap(energy=[_energy("m", "main", 0.4, 0.5)]))
        assert bd.charged_peak_kwh == pytest.approx(base.charged_peak_kwh)
        assert bd.observed_peak_kwh == pytest.approx(base.observed_peak_kwh)
        assert len(bd.stored_peaks) == len(base.stored_peaks)

    @pytest.mark.parametrize("curve_first", [True, False])
    def test_static_peak_used_regardless_of_order(self, curve_first):
        peak, curve = _peak(), _curve()
        power = [curve, peak] if curve_first else [peak, curve]
        _, bd = _run(_snap(power=power))
        _, base = _run(_snap(power=[peak]))
        assert base.peak_cost > 0
        assert bd.peak_cost == pytest.approx(base.peak_cost)
        assert bd.charged_peak_kwh == pytest.approx(base.charged_peak_kwh)
        assert bd.price_curve_cost == pytest.approx(10.0)
        assert bd.total == pytest.approx(base.peak_cost + 10.0)

    def test_peak_not_priced_with_curve_price(self):
        # Curve price must never be multiplied by the charged peak.
        _, bd = _run(_snap(power=[_curve(ex=80.0, inc=100.0)]))
        assert bd.peak_cost == 0.0


class TestUnchangedBehaviour:
    def test_static_tariff_has_no_curve_cost(self):
        snap = _snap(power=[_peak()], energy=[_energy("m", "main", 0.4, 0.5)])
        _, bd = _run(snap)
        assert bd.price_curve_cost == 0.0
        assert bd.transmission_cost == pytest.approx(5.0)
        assert bd.peak_cost > 0

    def test_energy_group_curve_unchanged(self):
        snap = _snap(energy=[_energy("c", "spot", 0.2, 0.25, url="/prices?x")])
        _, bd = _run(snap)
        assert bd.price_curve_cost == pytest.approx(2.5)


class TestCurrencyFallback:
    def test_currency_from_power_curve_only(self):
        _, bd = _run(_snap(power=[_curve(currency="EUR")]))
        assert bd.currency == "EUR"
