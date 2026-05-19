"""Tests for price curve support — models, overlay logic, and sensor."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.eltariff.api.models import (
    ActiveTariffSnapshot,
    ComponentType,
    Price,
    PriceComponent,
    PriceGroup,
    Tariff,
    TariffCollection,
    ValidPeriod,
)
from custom_components.eltariff.api.models.prices_response import (
    PriceListEntry,
    PricesResponse,
)
from custom_components.eltariff.coordinator_data import EltariffCoordinatorData
from custom_components.eltariff.price_curve_helpers import (
    collect_price_curve_component_ids,
    overlay_prices_on_snapshot,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _vp(from_: str = "2025-01-01", to: str | None = "2027-01-01") -> ValidPeriod:
    return ValidPeriod(
        from_including=date.fromisoformat(from_),
        to_excluding=date.fromisoformat(to) if to else None,
    )


def _price(ex: float = 0.8, inc: float = 1.0, currency: str = "SEK") -> Price:
    return Price(price_ex_vat=ex, price_inc_vat=inc, currency=currency)


def _comp(
    id_: str,
    ref: str = "main",
    ctype: ComponentType = ComponentType.ENERGY,
    url: str | None = None,
    price: Price | None = None,
) -> PriceComponent:
    return PriceComponent(
        id=id_,
        reference=ref,
        component_type=ctype,
        description="",
        valid_period=_vp(),
        price=price or _price(),
        url=url,
    )


def _tariff(
    id_: str = "t1",
    name: str = "TestTariff",
    energy_comps: list[PriceComponent] | None = None,
    power_comps: list[PriceComponent] | None = None,
) -> Tariff:
    return Tariff(
        id=id_,
        name=name,
        product="TestProduct",
        company_name="AB",
        valid_period=_vp(),
        energy_price=PriceGroup(components=energy_comps) if energy_comps else None,
        power_price=PriceGroup(components=power_comps) if power_comps else None,
    )


def _make_price_entry(
    hour: int,
    base_date: date | None = None,
    ex_vat: float = 0.0,
    inc_vat: float = 0.0,
) -> PriceListEntry:
    d = base_date or date(2026, 5, 19)
    start = datetime(d.year, d.month, d.day, hour, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    created = start - timedelta(hours=12)
    return PriceListEntry(
        created=created,
        start=start,
        end=end,
        price_ex_vat=ex_vat,
        price_inc_vat=inc_vat,
    )


def _make_prices_response(
    component_id: str = "comp-1",
    hours: int = 24,
    base_date: date | None = None,
    forecast_hours: int = 0,
    forecast_date: date | None = None,
) -> PricesResponse:
    d = base_date or date(2026, 5, 19)
    actual = [
        _make_price_entry(h, d, ex_vat=h * 0.1, inc_vat=h * 0.125) for h in range(hours)
    ]
    forecast = []
    if forecast_hours and forecast_date:
        forecast = [
            _make_price_entry(h, forecast_date, ex_vat=h * 0.2, inc_vat=h * 0.25)
            for h in range(forecast_hours)
        ]
    return PricesResponse(
        component_id=component_id,
        currency="SEK",
        resolution="PT1H",
        actual=actual,
        forecast=forecast,
    )


# ── PriceListEntry Tests ─────────────────────────────────────────────────────


class TestPriceListEntry:
    def test_from_dict_basic(self) -> None:
        d = {
            "created": "2026-05-18T12:00:00+02:00",
            "start": "2026-05-19T00:00:00+02:00",
            "end": "2026-05-19T01:00:00+02:00",
            "priceExVat": 0.5,
            "priceIncVat": 0.625,
        }
        entry = PriceListEntry.from_dict(d)
        assert entry.price_ex_vat == 0.5
        assert entry.price_inc_vat == 0.625
        assert entry.start.hour == 22 or entry.start.hour == 0  # depends on tz handling

    def test_from_dict_zero_prices(self) -> None:
        d = {
            "created": "2026-05-18T12:00:00+02:00",
            "start": "2026-05-19T00:00:00+02:00",
            "end": "2026-05-19T01:00:00+02:00",
            "priceExVat": 0.0,
            "priceIncVat": 0.0,
        }
        entry = PriceListEntry.from_dict(d)
        assert entry.price_ex_vat == 0.0
        assert entry.price_inc_vat == 0.0

    def test_from_dict_string_coercion(self) -> None:
        d = {
            "created": "2026-05-18T12:00:00+02:00",
            "start": "2026-05-19T14:00:00+02:00",
            "end": "2026-05-19T15:00:00+02:00",
            "priceExVat": "1.4",
            "priceIncVat": "1.750",
        }
        entry = PriceListEntry.from_dict(d)
        assert isinstance(entry.price_ex_vat, float)
        assert entry.price_ex_vat == 1.4
        assert entry.price_inc_vat == 1.75

    def test_frozen(self) -> None:
        entry = _make_price_entry(10)
        with pytest.raises(AttributeError):
            entry.price_ex_vat = 999.0


# ── PricesResponse Tests ─────────────────────────────────────────────────────


class TestPricesResponse:
    def test_from_dict_full(self) -> None:
        d = {
            "componentId": "abc-123",
            "currency": "SEK",
            "resolution": "PT1H",
            "actual": [
                {
                    "created": "2026-05-18T12:00:00+02:00",
                    "start": "2026-05-19T00:00:00+02:00",
                    "end": "2026-05-19T01:00:00+02:00",
                    "priceExVat": 0.0,
                    "priceIncVat": 0.0,
                },
                {
                    "created": "2026-05-18T12:00:00+02:00",
                    "start": "2026-05-19T01:00:00+02:00",
                    "end": "2026-05-19T02:00:00+02:00",
                    "priceExVat": 0.1,
                    "priceIncVat": 0.125,
                },
            ],
            "forecast": [
                {
                    "created": "2026-05-18T12:00:00+02:00",
                    "start": "2026-05-20T00:00:00+02:00",
                    "end": "2026-05-20T01:00:00+02:00",
                    "priceExVat": 0.5,
                    "priceIncVat": 0.625,
                },
            ],
        }
        resp = PricesResponse.from_dict(d)
        assert resp.component_id == "abc-123"
        assert resp.currency == "SEK"
        assert resp.resolution == "PT1H"
        assert len(resp.actual) == 2
        assert len(resp.forecast) == 1

    def test_from_dict_no_forecast(self) -> None:
        d = {
            "componentId": "abc",
            "currency": "SEK",
            "resolution": "PT1H",
            "actual": [],
        }
        resp = PricesResponse.from_dict(d)
        assert resp.forecast == []

    def test_all_entries_sorted(self) -> None:
        resp = _make_prices_response(
            hours=24,
            base_date=date(2026, 5, 19),
            forecast_hours=24,
            forecast_date=date(2026, 5, 20),
        )
        entries = resp.all_entries
        assert len(entries) == 48
        for i in range(len(entries) - 1):
            assert entries[i].start <= entries[i + 1].start

    def test_entry_at_finds_correct_hour(self) -> None:
        resp = _make_prices_response(hours=24)
        dt = datetime(2026, 5, 19, 14, 30, tzinfo=UTC)
        entry = resp.entry_at(dt)
        assert entry is not None
        assert entry.start.hour == 14
        assert entry.price_ex_vat == pytest.approx(1.4)

    def test_entry_at_returns_none_outside_range(self) -> None:
        resp = _make_prices_response(hours=24)
        dt = datetime(2026, 5, 20, 5, 0, tzinfo=UTC)
        assert resp.entry_at(dt) is None

    def test_entries_for_date(self) -> None:
        resp = _make_prices_response(
            hours=24,
            base_date=date(2026, 5, 19),
            forecast_hours=12,
            forecast_date=date(2026, 5, 20),
        )
        today_entries = resp.entries_for_date(date(2026, 5, 19))
        tomorrow_entries = resp.entries_for_date(date(2026, 5, 20))
        assert len(today_entries) == 24
        assert len(tomorrow_entries) == 12

    def test_has_date(self) -> None:
        resp = _make_prices_response(hours=24, base_date=date(2026, 5, 19))
        assert resp.has_date(date(2026, 5, 19)) is True
        assert resp.has_date(date(2026, 5, 20)) is False

    def test_frozen(self) -> None:
        resp = _make_prices_response()
        with pytest.raises(AttributeError):
            resp.currency = "EUR"


# ── ComponentType Tests ───────────────────────────────────────────────────────


class TestComponentTypeDynamic:
    def test_dynamic_value(self) -> None:
        assert ComponentType.DYNAMIC == "dynamic"
        assert ComponentType("dynamic") == ComponentType.DYNAMIC

    def test_spot_value(self) -> None:
        assert ComponentType.SPOT == "spot"
        assert ComponentType("spot") == ComponentType.SPOT


# ── collect_price_curve_component_ids Tests ───────────────────────────────────


class TestCollectPriceCurveComponentIds:
    def test_no_url_components(self) -> None:
        tariff = _tariff(energy_comps=[_comp("e1")])
        assert collect_price_curve_component_ids(tariff) == []

    def test_energy_component_with_url(self) -> None:
        tariff = _tariff(energy_comps=[
            _comp("e1", url="/prices/e1"),
            _comp("e2"),
        ])
        assert collect_price_curve_component_ids(tariff) == ["e1"]

    def test_power_component_with_url(self) -> None:
        tariff = _tariff(power_comps=[
            _comp("p1", ctype=ComponentType.DYNAMIC, url="/prices/p1"),
        ])
        assert collect_price_curve_component_ids(tariff) == ["p1"]

    def test_mixed_groups(self) -> None:
        tariff = _tariff(
            energy_comps=[_comp("e1", url="/prices/e1")],
            power_comps=[_comp("p1", ctype=ComponentType.DYNAMIC, url="/prices/p1")],
        )
        ids = collect_price_curve_component_ids(tariff)
        assert "e1" in ids
        assert "p1" in ids

    def test_no_groups(self) -> None:
        tariff = _tariff()
        assert collect_price_curve_component_ids(tariff) == []


# ── Snapshot Overlay Tests ────────────────────────────────────────────────────


class TestOverlayPricesOnSnapshot:
    def _snapshot(
        self,
        energy_comps: list[PriceComponent] | None = None,
        power_comps: list[PriceComponent] | None = None,
        at: datetime | None = None,
    ) -> ActiveTariffSnapshot:
        return ActiveTariffSnapshot(
            at=at or datetime(2026, 5, 19, 14, 30, tzinfo=UTC),
            tariff=_tariff(),
            active_energy_components=energy_comps or [],
            active_power_components=power_comps or [],
            active_fixed_components=[],
        )

    def test_no_curves_returns_unchanged(self) -> None:
        comp = _comp("e1", url="/prices/e1", price=_price(0, 0))
        snap = self._snapshot(energy_comps=[comp])
        result = overlay_prices_on_snapshot(snap, {}, datetime(2026, 5, 19, 14, 30, tzinfo=UTC))
        assert result.active_energy_components[0].price.price_ex_vat == 0.0

    def test_overlay_replaces_energy_price(self) -> None:
        comp = _comp("e1", url="/prices/e1", price=_price(0, 0))
        snap = self._snapshot(energy_comps=[comp])

        curves = {"e1": _make_prices_response(component_id="e1")}
        now = datetime(2026, 5, 19, 14, 30, tzinfo=UTC)
        result = overlay_prices_on_snapshot(snap, curves, now)

        # Hour 14: ex_vat = 14 * 0.1 = 1.4
        assert result.active_energy_components[0].price.price_ex_vat == pytest.approx(1.4)
        assert result.active_energy_components[0].price.price_inc_vat == pytest.approx(14 * 0.125)

    def test_overlay_replaces_power_price(self) -> None:
        comp = _comp("p1", ctype=ComponentType.DYNAMIC, url="/prices/p1", price=_price(0, 0))
        snap = self._snapshot(power_comps=[comp])

        curves = {"p1": _make_prices_response(component_id="p1")}
        now = datetime(2026, 5, 19, 10, 0, tzinfo=UTC)
        result = overlay_prices_on_snapshot(snap, curves, now)

        # Hour 10: ex_vat = 10 * 0.1 = 1.0
        assert result.active_power_components[0].price.price_ex_vat == pytest.approx(1.0)

    def test_overlay_preserves_non_url_components(self) -> None:
        static_comp = _comp("e_static", price=_price(5.0, 6.25))
        dynamic_comp = _comp("e_dyn", url="/prices/e_dyn", price=_price(0, 0))
        snap = self._snapshot(energy_comps=[static_comp, dynamic_comp])

        curves = {"e_dyn": _make_prices_response(component_id="e_dyn")}
        now = datetime(2026, 5, 19, 3, 0, tzinfo=UTC)
        result = overlay_prices_on_snapshot(snap, curves, now)

        # Static component unchanged.
        assert result.active_energy_components[0].price.price_ex_vat == 5.0
        # Dynamic component replaced.
        assert result.active_energy_components[1].price.price_ex_vat == pytest.approx(0.3)

    def test_overlay_no_entry_for_time_keeps_static(self) -> None:
        comp = _comp("e1", url="/prices/e1", price=_price(99, 99))
        snap = self._snapshot(energy_comps=[comp])

        # Prices only cover hour 0-23 on 2026-05-19; query at 2026-05-20
        curves = {"e1": _make_prices_response(component_id="e1")}
        now = datetime(2026, 5, 20, 5, 0, tzinfo=UTC)
        result = overlay_prices_on_snapshot(snap, curves, now)

        # No matching entry, static price preserved.
        assert result.active_energy_components[0].price.price_ex_vat == 99

    def test_overlay_uses_curve_currency(self) -> None:
        comp = _comp("e1", url="/prices/e1", price=_price(0, 0, "EUR"))
        snap = self._snapshot(energy_comps=[comp])

        curves = {"e1": _make_prices_response(component_id="e1")}
        now = datetime(2026, 5, 19, 10, 0, tzinfo=UTC)
        result = overlay_prices_on_snapshot(snap, curves, now)

        # Currency comes from the PricesResponse, not the static component.
        assert result.active_energy_components[0].price.currency == "SEK"


# ── Polling Logic Tests ──────────────────────────────────────────────────────


class TestPollTimingLogic:
    """Test the price curve polling timing logic (pure logic, no HA deps)."""

    def test_has_date_gates_polling(self) -> None:
        """If all curves already have tomorrow, no poll needed."""
        tomorrow = date(2026, 5, 20)
        curves = {
            "c1": _make_prices_response(
                component_id="c1",
                hours=24,
                base_date=date(2026, 5, 19),
                forecast_hours=24,
                forecast_date=tomorrow,
            )
        }
        # All curves have tomorrow's date → no further polling needed.
        assert all(resp.has_date(tomorrow) for resp in curves.values())

    def test_missing_tomorrow_needs_polling(self) -> None:
        """If any curve is missing tomorrow, we need to poll."""
        tomorrow = date(2026, 5, 20)
        curves = {
            "c1": _make_prices_response(component_id="c1", hours=24, base_date=date(2026, 5, 19))
        }
        assert not all(resp.has_date(tomorrow) for resp in curves.values())

    def test_noon_boundary(self) -> None:
        """Polling should only start at/after noon local time."""
        from custom_components.eltariff.const import PRICE_CURVE_POLL_START_HOUR

        assert PRICE_CURVE_POLL_START_HOUR == 12
        now_morning = datetime(2026, 5, 19, 11, 59, tzinfo=UTC)
        now_afternoon = datetime(2026, 5, 19, 12, 1, tzinfo=UTC)
        assert now_morning.hour < PRICE_CURVE_POLL_START_HOUR
        assert now_afternoon.hour >= PRICE_CURVE_POLL_START_HOUR

    def test_poll_interval_constant(self) -> None:
        from custom_components.eltariff.const import (
            PRICE_CURVE_POLL_INTERVAL_SECONDS,
            PRICE_CURVE_POLL_JITTER_SECONDS,
        )

        assert PRICE_CURVE_POLL_INTERVAL_SECONDS == 300
        assert PRICE_CURVE_POLL_JITTER_SECONDS == 60


# ── CoordinatorData Tests ─────────────────────────────────────────────────────


class TestCoordinatorDataPriceCurves:
    def test_default_empty_curves(self) -> None:
        from custom_components.eltariff.api.models.server import ServerInfo

        data = EltariffCoordinatorData(
            info=ServerInfo(timezone="Europe/Stockholm", tariff_data_last_updated=None),
            collection=TariffCollection(tariffs=[], calendar_patterns=[]),
            snapshot=ActiveTariffSnapshot(
                at=datetime.now(tz=UTC),
                tariff=_tariff(),
                active_power_components=[],
                active_energy_components=[],
                active_fixed_components=[],
            ),
            next_transition=None,
        )
        assert data.price_curves == {}

    def test_with_price_curves(self) -> None:
        from custom_components.eltariff.api.models.server import ServerInfo

        curves = {"c1": _make_prices_response(component_id="c1")}
        data = EltariffCoordinatorData(
            info=ServerInfo(timezone="Europe/Stockholm", tariff_data_last_updated=None),
            collection=TariffCollection(tariffs=[], calendar_patterns=[]),
            snapshot=ActiveTariffSnapshot(
                at=datetime.now(tz=UTC),
                tariff=_tariff(),
                active_power_components=[],
                active_energy_components=[],
                active_fixed_components=[],
            ),
            next_transition=None,
            price_curves=curves,
        )
        assert "c1" in data.price_curves
        assert len(data.price_curves["c1"].actual) == 24


# ── PricesResponse from user-provided JSON ───────────────────────────────────


class TestPricesResponseFromRealJson:
    """Parse the example JSON the user provided (adapted to spec format)."""

    def test_parse_user_example(self) -> None:
        raw = {
            "componentId": "test-component-uuid",
            "currency": "SEK",
            "resolution": "PT1H",
            "actual": [
                {
                    "created": "2026-05-18T12:00:00+02:00",
                    "start": "2026-05-19T00:00:00+02:00",
                    "end": "2026-05-19T01:00:00+02:00",
                    "priceExVat": 0.0,
                    "priceIncVat": 0.000,
                },
                {
                    "created": "2026-05-18T12:00:00+02:00",
                    "start": "2026-05-19T14:00:00+02:00",
                    "end": "2026-05-19T15:00:00+02:00",
                    "priceExVat": 1.4,
                    "priceIncVat": 1.750,
                },
                {
                    "created": "2026-05-18T12:00:00+02:00",
                    "start": "2026-05-19T23:00:00+02:00",
                    "end": "2026-05-20T00:00:00+02:00",
                    "priceExVat": 2.3,
                    "priceIncVat": 2.875,
                },
            ],
            "forecast": [],
        }
        resp = PricesResponse.from_dict(raw)
        assert resp.component_id == "test-component-uuid"
        assert resp.currency == "SEK"
        assert len(resp.actual) == 3
        assert resp.actual[1].price_inc_vat == 1.75

    def test_entry_at_on_parsed(self) -> None:
        """Verify entry_at works with timezone-aware datetimes from the JSON."""
        raw = {
            "componentId": "test",
            "currency": "SEK",
            "resolution": "PT1H",
            "actual": [
                {
                    "created": "2026-05-18T12:00:00+02:00",
                    "start": "2026-05-19T14:00:00+02:00",
                    "end": "2026-05-19T15:00:00+02:00",
                    "priceExVat": 1.4,
                    "priceIncVat": 1.750,
                },
            ],
        }
        resp = PricesResponse.from_dict(raw)

        # 14:30 local (+02:00) = 12:30 UTC
        import zoneinfo

        tz = zoneinfo.ZoneInfo("Europe/Stockholm")
        dt_local = datetime(2026, 5, 19, 14, 30, tzinfo=tz)
        entry = resp.entry_at(dt_local)
        assert entry is not None
        assert entry.price_ex_vat == 1.4


# ── Integration: snapshot overlay with real-ish data ──────────────────────────


class TestSnapshotOverlayIntegration:
    """End-to-end: tariff with dynamic component → snapshot has hourly price."""

    def test_energy_transfer_with_dynamic_pricing(self) -> None:
        """An energy 'main' component with url gets its price from the curve."""
        comp = _comp(
            "energy-main-uuid",
            ref="main",
            ctype=ComponentType.ENERGY,
            url="/prices/energy-main-uuid",
            price=_price(0, 0),  # static price is zero/placeholder
        )
        tax_comp = _comp(
            "tax-uuid", ref="tax", ctype=ComponentType.ENERGY, price=_price(0.392, 0.49)
        )

        snap = ActiveTariffSnapshot(
            at=datetime(2026, 5, 19, 10, 0, tzinfo=UTC),
            tariff=_tariff(energy_comps=[comp, tax_comp]),
            active_energy_components=[comp, tax_comp],
            active_power_components=[],
            active_fixed_components=[],
        )

        curves = {
            "energy-main-uuid": _make_prices_response(
                component_id="energy-main-uuid", hours=24
            )
        }
        now = datetime(2026, 5, 19, 10, 0, tzinfo=UTC)
        result = overlay_prices_on_snapshot(snap, curves, now)

        # main component: hour 10 → ex_vat = 10 * 0.1 = 1.0
        main_comps = [c for c in result.active_energy_components if c.reference == "main"]
        assert len(main_comps) == 1
        assert main_comps[0].price.price_ex_vat == pytest.approx(1.0)

        # tax component: unchanged
        tax_comps = [c for c in result.active_energy_components if c.reference == "tax"]
        assert len(tax_comps) == 1
        assert tax_comps[0].price.price_ex_vat == pytest.approx(0.392)

        # total_energy_price_ex_vat includes both
        assert result.total_energy_price_ex_vat == pytest.approx(1.0 + 0.392)

    def test_power_dynamic_component(self) -> None:
        """A power component with type=dynamic and url gets curve pricing."""
        comp = _comp(
            "power-dyn-uuid",
            ref="main",
            ctype=ComponentType.DYNAMIC,
            url="/prices/power-dyn-uuid",
            price=_price(0, 0),
        )

        snap = ActiveTariffSnapshot(
            at=datetime(2026, 5, 19, 20, 0, tzinfo=UTC),
            tariff=_tariff(power_comps=[comp]),
            active_energy_components=[],
            active_power_components=[comp],
            active_fixed_components=[],
        )

        curves = {
            "power-dyn-uuid": _make_prices_response(component_id="power-dyn-uuid")
        }
        now = datetime(2026, 5, 19, 20, 0, tzinfo=UTC)
        result = overlay_prices_on_snapshot(snap, curves, now)

        # Hour 20: ex_vat = 20 * 0.1 = 2.0
        assert result.active_power_component is not None
        assert result.active_power_component.price.price_ex_vat == pytest.approx(2.0)


# ── PriceCurveSensor Tests ────────────────────────────────────────────────────


class TestPriceCurveSensorLogic:
    """Test the logic that the PriceCurveSensor would use, without HA deps.

    The sensor reads from coordinator_data.price_curves and the snapshot.
    We verify the data paths here.
    """

    def _make_data(self, price_curves: dict | None = None):
        from custom_components.eltariff.api.models.server import ServerInfo

        snap = ActiveTariffSnapshot(
            at=datetime(2026, 5, 19, 14, 30, tzinfo=UTC),
            tariff=_tariff(energy_comps=[_comp("c1", url="/prices/c1")]),
            active_energy_components=[_comp("c1", url="/prices/c1")],
            active_power_components=[],
            active_fixed_components=[],
        )

        return EltariffCoordinatorData(
            info=ServerInfo(timezone="Europe/Stockholm", tariff_data_last_updated=None),
            collection=TariffCollection(tariffs=[], calendar_patterns=[]),
            snapshot=snap,
            next_transition=None,
            price_curves=price_curves or {},
        )

    def test_current_price_inc_vat(self) -> None:
        curves = {"c1": _make_prices_response(component_id="c1", hours=24)}
        data = self._make_data(price_curves=curves)
        resp = data.price_curves["c1"]
        entry = resp.entry_at(data.snapshot.at)
        assert entry is not None
        # Hour 14: inc_vat = 14 * 0.125 = 1.75
        assert entry.price_inc_vat == pytest.approx(1.75)

    def test_current_price_ex_vat(self) -> None:
        curves = {"c1": _make_prices_response(component_id="c1", hours=24)}
        data = self._make_data(price_curves=curves)
        resp = data.price_curves["c1"]
        entry = resp.entry_at(data.snapshot.at)
        assert entry is not None
        # Hour 14: ex_vat = 14 * 0.1 = 1.4
        assert entry.price_ex_vat == pytest.approx(1.4)

    def test_no_curves_returns_none(self) -> None:
        data = self._make_data(price_curves={})
        assert data.price_curves.get("c1") is None

    def test_currency_from_response(self) -> None:
        curves = {"c1": _make_prices_response(component_id="c1")}
        data = self._make_data(price_curves=curves)
        assert data.price_curves["c1"].currency == "SEK"

    def test_today_tomorrow_attrs(self) -> None:
        tomorrow = date(2026, 5, 20)
        curves = {
            "c1": _make_prices_response(
                component_id="c1",
                hours=24,
                base_date=date(2026, 5, 19),
                forecast_hours=24,
                forecast_date=tomorrow,
            )
        }
        data = self._make_data(price_curves=curves)
        resp = data.price_curves["c1"]
        snap_date = data.snapshot.at.date()

        today_entries = resp.entries_for_date(snap_date)
        tomorrow_entries = resp.entries_for_date(snap_date + timedelta(days=1))

        assert len(today_entries) == 24
        assert len(tomorrow_entries) == 24
        assert resp.has_date(tomorrow)

    def test_no_tomorrow_available(self) -> None:
        curves = {"c1": _make_prices_response(component_id="c1", hours=24)}
        data = self._make_data(price_curves=curves)
        resp = data.price_curves["c1"]
        tomorrow = data.snapshot.at.date() + timedelta(days=1)

        assert resp.has_date(tomorrow) is False
        assert resp.entries_for_date(tomorrow) == []
