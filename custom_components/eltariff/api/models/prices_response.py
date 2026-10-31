"""PriceListEntry and PricesResponse dataclasses for the /prices endpoint."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SWEDISH_VAT = 1.25


@dataclass(frozen=True)
class PriceListEntry:
    """A single timed price entry from the /prices endpoint."""

    created: datetime | None
    start: datetime
    end: datetime
    price_ex_vat: float
    price_inc_vat: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PriceListEntry:
        # Per the spec only start, end and priceExVat are required.
        price_ex_vat = float(d["priceExVat"])
        raw_inc = d.get("priceIncVat")
        return cls(
            created=datetime.fromisoformat(d["created"]) if d.get("created") else None,
            start=datetime.fromisoformat(d["start"]),
            end=datetime.fromisoformat(d["end"]),
            price_ex_vat=price_ex_vat,
            price_inc_vat=(
                float(raw_inc) if raw_inc is not None else round(price_ex_vat * SWEDISH_VAT, 6)
            ),
        )


def _infer_resolution(entries: list[PriceListEntry]) -> str:
    """The spec has no resolution field; derive it from the first entry (default hourly)."""
    if entries:
        minutes = round((entries[0].end - entries[0].start).total_seconds() / 60)
        if minutes > 0 and minutes % 60 == 0:
            return f"PT{minutes // 60}H"
        if minutes > 0:
            return f"PT{minutes}M"
    return "PT1H"


@dataclass(frozen=True)
class PricesResponse:
    """Response from GET /prices/{componentId}."""

    component_id: str
    currency: str
    resolution: str
    actual: list[PriceListEntry]
    forecast: list[PriceListEntry] = field(default_factory=list)
    time_zone: str | None = None
    unit: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PricesResponse:
        actual = [PriceListEntry.from_dict(e) for e in d.get("actual") or []]
        return cls(
            component_id=d.get("componentId", ""),
            currency=d["currency"],
            resolution=d.get("resolution") or _infer_resolution(actual),
            actual=actual,
            # Some DSOs publish future prices as "preview" instead of "forecast".
            forecast=[
                PriceListEntry.from_dict(e)
                for e in (d.get("forecast") or []) + (d.get("preview") or [])
            ],
            time_zone=d.get("timeZone"),
            unit=d.get("unit"),
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
