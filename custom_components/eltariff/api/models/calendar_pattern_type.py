"""CalendarPatternType enumeration."""
from __future__ import annotations

from enum import StrEnum


class CalendarPatternType(StrEnum):
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    HOLIDAYS = "holidays"
