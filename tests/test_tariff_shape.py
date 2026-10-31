"""Tariff shape checks that decide which sensors are created."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.eltariff.api.models import Tariff, TariffCollection
from custom_components.eltariff.tariff_shape import (
    has_banded_power,
    has_energy_reference,
    has_fixed_price,
)

VALID = {"fromIncluding": "2026-12-01", "toExcluding": "2028-01-01"}
PRICE = {"priceExVat": 1.0, "priceIncVat": 1.25, "currency": "SEK"}


def _comp(reference: str, type_: str = "fixed", **extra) -> dict:
    return {
        "id": f"c-{reference}",
        "reference": reference,
        "type": type_,
        "validPeriod": VALID,
        "price": PRICE,
        **extra,
    }


def _tariff(fixed=None, energy=None, power=None) -> Tariff:
    d = {
        "id": "t",
        "name": "T",
        "validPeriod": VALID,
        "companyName": "X",
        "product": "P",
    }
    for key, comps in (("fixedPrice", fixed), ("energyPrice", energy), ("powerPrice", power)):
        if comps is not None:
            d[key] = {"components": comps}
    return Tariff.from_dict(d)


def test_hourly_tariff_has_no_bands() -> None:
    tariff = _tariff(
        fixed=[_comp("main", pricedPeriod="P1Y")],
        energy=[_comp("main"), _comp("tax")],
        power=[_comp("hourly", "dynamic", price=None, url="/prices?product=X")],
    )
    assert not has_banded_power(tariff)
    assert has_energy_reference(tariff, "main")
    assert has_energy_reference(tariff, "tax")
    assert has_fixed_price(tariff)


def test_peak_tariff_has_bands() -> None:
    tariff = _tariff(
        fixed=[_comp("main", pricedPeriod="P1Y")],
        energy=[_comp("main"), _comp("tax")],
        power=[_comp("high", "peak"), _comp("low", "peak")],
    )
    assert has_banded_power(tariff)


def test_missing_groups() -> None:
    tariff = _tariff(energy=[_comp("main")])
    assert not has_banded_power(tariff)
    assert not has_fixed_price(tariff)
    assert has_energy_reference(tariff, "main")
    assert not has_energy_reference(tariff, "tax")


def test_sample_tariffs_with_static_power_keep_band_sensors() -> None:
    path = Path(__file__).parent.parent / "samples" / "goteborg_tariffs.json"
    if not path.exists():
        pytest.skip("Run scripts/dump_tariff.py first to generate sample data")
    collection = TariffCollection.from_dict(json.loads(path.read_text()))
    for tariff in collection.tariffs:
        power = tariff.power_price.components if tariff.power_price else []
        assert has_banded_power(tariff) == any(c.url is None for c in power)
