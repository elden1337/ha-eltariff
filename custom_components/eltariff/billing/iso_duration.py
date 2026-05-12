"""ISO 8601 duration parsing and period boundary utilities."""
from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class ParsedDuration:
    """Parsed ISO 8601 duration components."""

    years: int = 0
    months: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0

    @property
    def is_calendar(self) -> bool:
        """True if the duration uses calendar units (years/months)."""
        return self.years > 0 or self.months > 0


_ISO_DURATION_RE = re.compile(
    r"^P"
    r"(?:(\d+)Y)?"
    r"(?:(\d+)M)?"
    r"(?:(\d+)D)?"
    r"(?:T"
    r"(?:(\d+)H)?"
    r"(?:(\d+)M)?"
    r")?"
    r"$"
)


def parse_iso_duration(value: str) -> ParsedDuration:
    """Parse an ISO 8601 duration string (e.g. 'P1M', 'P1D', 'PT1H')."""
    m = _ISO_DURATION_RE.match(value)
    if not m:
        raise ValueError(f"Invalid ISO 8601 duration: {value!r}")
    return ParsedDuration(
        years=int(m.group(1) or 0),
        months=int(m.group(2) or 0),
        days=int(m.group(3) or 0),
        hours=int(m.group(4) or 0),
        minutes=int(m.group(5) or 0),
    )


def period_start(dt: datetime, duration: ParsedDuration) -> datetime:
    """Return the start of the period that *dt* falls into.

    For calendar durations the start is aligned to calendar boundaries:
    - P1M → first of the month
    - P1Y → January 1st
    - P3M → start of the calendar quarter

    For fixed durations (days / hours / minutes) the start is aligned to
    midnight (for days) or the most recent boundary for sub-day durations.
    """
    if duration.years:
        return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if duration.months:
        # Align to the start of a month-group.
        # E.g. P3M → quarters: Jan, Apr, Jul, Oct.
        month_group = ((dt.month - 1) // duration.months) * duration.months + 1
        return dt.replace(month=month_group, day=1, hour=0, minute=0, second=0, microsecond=0)
    if duration.days:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if duration.hours:
        aligned_hour = (dt.hour // duration.hours) * duration.hours
        return dt.replace(hour=aligned_hour, minute=0, second=0, microsecond=0)
    if duration.minutes:
        aligned_minute = (dt.minute // duration.minutes) * duration.minutes
        return dt.replace(minute=aligned_minute, second=0, microsecond=0)
    return dt


def period_end(dt: datetime, duration: ParsedDuration) -> datetime:
    """Return the exclusive end of the period that *dt* falls into."""
    start = period_start(dt, duration)
    return _add_duration(start, duration)


def is_same_period(dt1: datetime, dt2: datetime, duration: ParsedDuration) -> bool:
    """Check whether *dt1* and *dt2* fall into the same period."""
    return period_start(dt1, duration) == period_start(dt2, duration)


def _add_duration(dt: datetime, duration: ParsedDuration) -> datetime:
    """Add a parsed duration to a datetime."""
    if duration.years or duration.months:
        total_months = dt.month - 1 + duration.years * 12 + duration.months
        new_year = dt.year + total_months // 12
        new_month = total_months % 12 + 1
        max_day = monthrange(new_year, new_month)[1]
        return dt.replace(year=new_year, month=new_month, day=min(dt.day, max_day))
    return dt + timedelta(
        days=duration.days,
        hours=duration.hours,
        minutes=duration.minutes,
    )


def elapsed_fraction(dt: datetime, duration: ParsedDuration) -> float:
    """Return how far *dt* is through its current period (0.0 → 1.0)."""
    start = period_start(dt, duration)
    end = period_end(dt, duration)
    total = (end - start).total_seconds()
    if total <= 0:
        return 0.0
    elapsed = (dt - start).total_seconds()
    return max(0.0, min(1.0, elapsed / total))


def days_in_period(dt: datetime, duration: ParsedDuration) -> float:
    """Return total days in the period that *dt* falls into."""
    start = period_start(dt, duration)
    end = period_end(dt, duration)
    return (end - start).total_seconds() / 86400.0
