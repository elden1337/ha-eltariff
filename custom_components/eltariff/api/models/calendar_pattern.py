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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalendarPattern:
        id_ = d.get("id") or d.get("reference", "")
        if "type" in d:
            pattern_type = CalendarPatternType(d["type"])
        else:
            days = set(d.get("days", []))
            if days & {6, 7}:
                pattern_type = CalendarPatternType.WEEKENDS
            elif days & {1, 2, 3, 4, 5}:
                pattern_type = CalendarPatternType.WEEKDAYS
            else:
                pattern_type = CalendarPatternType.HOLIDAYS
        return cls(
            id=id_,
            name=d.get("name", ""),
            pattern_type=pattern_type,
            dates=[date.fromisoformat(dt) for dt in d.get("dates", [])],
        )
