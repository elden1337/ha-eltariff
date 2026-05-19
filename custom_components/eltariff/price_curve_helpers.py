"""Pure functions for price curve overlay and detection.

These are separated from the coordinator so they can be unit-tested
without HA dependencies.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .api.models import (
    ActiveTariffSnapshot,
    Price,
    PriceComponent,
    Tariff,
)
from .api.models.prices_response import PricesResponse


def collect_price_curve_component_ids(tariff: Tariff) -> list[str]:
    """Return component IDs that need price curve fetching (have a url set)."""
    ids: list[str] = []
    for group in (tariff.energy_price, tariff.power_price):
        if group is None:
            continue
        for comp in group.components:
            if comp.url:
                ids.append(comp.id)
    return ids


def overlay_prices_on_snapshot(
    snapshot: ActiveTariffSnapshot,
    price_curves: dict[str, PricesResponse],
    now: datetime,
) -> ActiveTariffSnapshot:
    """Replace static prices with fetched hourly prices for components that have url set."""
    if not price_curves:
        return snapshot

    def _maybe_replace(components: list[PriceComponent]) -> list[PriceComponent]:
        result = []
        for comp in components:
            if comp.url and comp.id in price_curves:
                entry = price_curves[comp.id].entry_at(now)
                if entry is not None:
                    new_price = Price(
                        price_ex_vat=entry.price_ex_vat,
                        price_inc_vat=entry.price_inc_vat,
                        currency=price_curves[comp.id].currency,
                    )
                    comp = replace(comp, price=new_price)
            result.append(comp)
        return result

    snapshot.active_energy_components = _maybe_replace(snapshot.active_energy_components)
    snapshot.active_power_components = _maybe_replace(snapshot.active_power_components)
    return snapshot
