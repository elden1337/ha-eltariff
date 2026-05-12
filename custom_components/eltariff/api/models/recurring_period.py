"""RecurringPeriod dataclass."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .active_period import ActivePeriod


@dataclass
class RecurringPeriod:
    active_periods: list[ActivePeriod]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RecurringPeriod:
        return cls(
            active_periods=[ActivePeriod.from_dict(p) for p in d.get("activePeriods", [])]
        )
