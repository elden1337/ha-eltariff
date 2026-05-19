"""PriceListEntry and PricesResponse dataclasses for the /prices endpoint."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PriceListEntry:
    """A single timed price entry from the /prices endpoint."""

    created: datetime
    start: datetime
    end: datetime
    price_ex_vat: float
    price_inc_vat: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PriceListEntry:
        return cls(
            created=datetime.fromisoformat(d["created"]),
            start=datetime.fromisoformat(d["start"]),
            end=datetime.fromisoformat(d["end"]),
            price_ex_vat=float(d["priceExVat"]),
            price_inc_vat=float(d["priceIncVat"]),
        )


@dataclass(frozen=True)
class PricesResponse:
    """Response from GET /prices/{componentId}."""

    component_id: str
    currency: str
    resolution: str
    actual: list[PriceListEntry]
    forecast: list[PriceListEntry] = field(default_factory=list)
    time_zone: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PricesResponse:
        return cls(
            component_id=d.get("componentId", ""),
            currency=d["currency"],
            resolution=d.get("resolution", "PT1H"),
            actual=[PriceListEntry.from_dict(e) for e in d.get("actual", [])],
            forecast=[PriceListEntry.from_dict(e) for e in d.get("forecast", [])],
            time_zone=d.get("timeZone"),
        )

    @property
    def all_entries(self) -> list[PriceListEntry]:
        """All entries (actual + forecast), sorted by start time."""
        combined = list(self.actual) + list(self.forecast)
        return sorted(combined, key=lambda e: e.start)

    def entry_at(self, dt: datetime) -> PriceListEntry | None:
        """Find the price entry covering *dt* (start <= dt < end)."""
        for entry in self.all_entries:
            if entry.start <= dt < entry.end:
                return entry
        return None

    def entries_for_date(self, target_date) -> list[PriceListEntry]:
        """Return all entries whose start falls on *target_date*."""
        return [e for e in self.all_entries if e.start.date() == target_date]

    def has_date(self, target_date) -> bool:
        """Return True if any entry starts on *target_date*."""
        return any(e.start.date() == target_date for e in self.all_entries)
