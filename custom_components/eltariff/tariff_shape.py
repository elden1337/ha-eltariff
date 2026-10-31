"""Structural questions about a tariff, independent of what is active right now."""

from __future__ import annotations

from .api.models import PriceComponent, Tariff


def _components(tariff: Tariff, group_name: str) -> list[PriceComponent]:
    group = getattr(tariff, group_name)
    return list(group.components) if group else []


def has_banded_power(tariff: Tariff) -> bool:
    """True if the tariff has power components with a static price (bands / peaks).

    Components with a url are dynamic price curves (e.g. hourly power price) and
    have no bands or peaks to report.
    """
    return any(c.url is None for c in _components(tariff, "power_price"))


def has_energy_reference(tariff: Tariff, reference: str) -> bool:
    return any(c.reference == reference for c in _components(tariff, "energy_price"))


def has_fixed_price(tariff: Tariff) -> bool:
    return bool(_components(tariff, "fixed_price"))
