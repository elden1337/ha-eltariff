"""RecurringPeriod dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .active_period import ActivePeriod


@dataclass(frozen=True)
class RecurringPeriod:
    active_periods: list[ActivePeriod]
    reference: str | None = None
    # ISO 8601 duration string (e.g. "PT15M", "PT1H")
    frequency: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RecurringPeriod:
        return cls(
            active_periods=[ActivePeriod.from_dict(p) for p in d.get("activePeriods", [])],
            reference=d.get("reference"),
            frequency=d.get("frequency"),
        )
