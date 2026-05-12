"""Backward-compatible re-exports for schedule-related models.

All classes have been moved to their own modules. This shim preserves
any imports that reference ``api.models.schedule`` directly.
"""

from __future__ import annotations

from .active_period import ActivePeriod
from .calendar_pattern import CalendarPattern
from .calendar_pattern_references import CalendarPatternReferences
from .calendar_pattern_type import CalendarPatternType
from .peak_identification_settings import PeakIdentificationSettings
from .recurring_period import RecurringPeriod
from .valid_period import ValidPeriod

__all__ = [
    "ActivePeriod",
    "CalendarPattern",
    "CalendarPatternReferences",
    "CalendarPatternType",
    "PeakIdentificationSettings",
    "RecurringPeriod",
    "ValidPeriod",
]
