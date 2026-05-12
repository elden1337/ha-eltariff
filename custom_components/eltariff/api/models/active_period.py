"""ActivePeriod dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from .calendar_pattern_references import CalendarPatternReferences


@dataclass(frozen=True)
class ActivePeriod:
    """A time-of-day band within a recurring period."""

    from_including: time
    to_excluding: time  # 00:00:00 when from_including != 00:00:00 means end-of-day
    calendar_pattern_references: CalendarPatternReferences

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ActivePeriod:
        return cls(
            from_including=time.fromisoformat(d["fromIncluding"]),
            to_excluding=time.fromisoformat(d["toExcluding"]),
            calendar_pattern_references=CalendarPatternReferences.from_dict(
                d.get("calendarPatternReferences", {})
            ),
        )

    def time_matches(self, dt: datetime) -> bool:
        t = dt.time().replace(second=0, microsecond=0)
        start = self.from_including
        end = self.to_excluding
        # Full-day convention: both are midnight
        if start == time(0, 0) and end == time(0, 0):
            return True
        # End-of-day convention: end is midnight but start is not
        if end == time(0, 0):
            return t >= start
        return start <= t < end
