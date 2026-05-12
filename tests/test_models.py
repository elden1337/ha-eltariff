"""Basic smoke tests for model parsing."""
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from custom_components.eltariff.api.models import Tariff, TariffCollection, ValidPeriod

SAMPLES = Path(__file__).parent.parent / "samples"


@pytest.fixture
def goteborg_collection() -> TariffCollection:
    path = SAMPLES / "goteborg_tariffs.json"
    if not path.exists():
        pytest.skip("Run scripts/dump_tariff.py first to generate sample data")
    return TariffCollection.from_dict(json.loads(path.read_text()))


def test_tariff_collection_parses(goteborg_collection: TariffCollection) -> None:
    assert len(goteborg_collection.tariffs) > 0
    assert len(goteborg_collection.calendar_patterns) > 0


def test_all_components_have_price(goteborg_collection: TariffCollection) -> None:
    for tariff in goteborg_collection.tariffs:
        for group in (tariff.fixed_price, tariff.energy_price, tariff.power_price):
            if group is None:
                continue
            for comp in group.components:
                assert comp.price.currency != ""
                assert comp.price.price_inc_vat >= 0


def test_calendar_pattern_types(goteborg_collection: TariffCollection) -> None:
    types = {p.pattern_type for p in goteborg_collection.calendar_patterns}
    assert len(types) > 0


def test_find_tariff_by_name_prefers_active_valid_period() -> None:
    old_tariff = Tariff(
        id="old-id",
        name="Villa",
        product="P",
        company_name="Grid AB",
        valid_period=ValidPeriod(from_including=date(2024, 1, 1), to_excluding=date(2025, 1, 1)),
    )
    current_tariff = Tariff(
        id="new-id",
        name="Villa",
        product="P",
        company_name="Grid AB",
        valid_period=ValidPeriod(from_including=date(2025, 1, 1), to_excluding=None),
    )
    collection = TariffCollection(tariffs=[old_tariff, current_tariff], calendar_patterns=[])

    selected = collection.find_tariff_by_name(
        "Villa",
        at=datetime(2025, 5, 1, 12, 0, tzinfo=UTC),
    )

    assert selected is not None
    assert selected.id == "new-id"
