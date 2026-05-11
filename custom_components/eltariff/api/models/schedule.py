"""Schedule and calendar-related dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any


class CalendarPatternType(StrEnum):
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    HOLIDAYS = "holidays"


@dataclass
class ValidPeriod:
    from_including: date
    to_excluding: date | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ValidPeriod:
        return cls(
            from_including=date.fromisoformat(d["fromIncluding"]),
            to_excluding=date.fromisoformat(d["toExcluding"]) if d.get("toExcluding") else None,
        )

    def contains(self, dt: datetime) -> bool:
        if dt.date() < self.from_including:
            return False
        if self.to_excluding is not None and dt.date() >= self.to_excluding:
            return False
        return True


@dataclass
class CalendarPatternReferences:
    include: list[str]
    exclude: list[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalendarPatternReferences:
        return cls(
            include=list(d.get("include", [])),
            exclude=list(d.get("exclude", [])),
        )


@dataclass
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


@dataclass
class RecurringPeriod:
    active_periods: list[ActivePeriod]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RecurringPeriod:
        return cls(
            active_periods=[ActivePeriod.from_dict(p) for p in d.get("activePeriods", [])]
        )


@dataclass
class PeakIdentificationSettings:
    number_of_peaks_for_average: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PeakIdentificationSettings:
        return cls(
            number_of_peaks_for_average=int(d["numberOfPeaksForAverageCalculation"])
        )


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
