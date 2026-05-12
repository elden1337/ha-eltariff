"""CalendarPattern dataclass."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .calendar_pattern_type import CalendarPatternType


@dataclass
class CalendarPattern:
    id: str
    name: str
    pattern_type: CalendarPatternType
    dates: list[date] = field(default_factory=list)
    days: list[int] = field(default_factory=list)
    # ISO 8601 duration string (e.g. "PT15M")
    frequency: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalendarPattern:
        id_ = d.get("id") or d.get("reference", "")
        days = list(d.get("days", []))
        if "type" in d:
            pattern_type = CalendarPatternType(d["type"])
        else:
            days_set = set(days)
            if days_set & {6, 7}:
                pattern_type = CalendarPatternType.WEEKENDS
            elif days_set & {1, 2, 3, 4, 5}:
                pattern_type = CalendarPatternType.WEEKDAYS
            else:
                pattern_type = CalendarPatternType.HOLIDAYS
        return cls(
            id=id_,
            name=d.get("name", ""),
            pattern_type=pattern_type,
            dates=[date.fromisoformat(dt) for dt in d.get("dates", [])],
            days=days,
            frequency=d.get("frequency"),
        )
