"""TariffCollection dataclass."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .calendar_pattern import CalendarPattern
from .tariff import Tariff


@dataclass
class TariffCollection:
    tariffs: list[Tariff]
    calendar_patterns: list[CalendarPattern]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TariffCollection:
        # The API may return either a list ("tariffs") or a single object ("tariff")
        if "tariffs" in d:
            tariffs = [Tariff.from_dict(t) for t in d["tariffs"]]
        elif "tariff" in d:
            tariffs = [Tariff.from_dict(d["tariff"])]
        else:
            tariffs = []
        return cls(
            tariffs=tariffs,
            calendar_patterns=[CalendarPattern.from_dict(p) for p in d.get("calendarPatterns", [])],
        )

    def get_tariff(self, tariff_id: str) -> Tariff | None:
        return next((t for t in self.tariffs if t.id == tariff_id), None)

    def find_tariff_by_name(self, name: str, at: datetime | None = None) -> Tariff | None:
        """Find tariff by stable display name.

        If *at* is provided, active matches are preferred. When several active
        matches exist, the tariff with the latest ``from_including`` is chosen.
        If *at* is not provided, the latest ``from_including`` match is returned.
        """
        candidates = [t for t in self.tariffs if t.name == name]
        if not candidates:
            return None

        if at is not None:
            active_candidates = [t for t in candidates if t.valid_period.contains(at)]
            if active_candidates:
                return max(active_candidates, key=lambda t: t.valid_period.from_including)

        return max(candidates, key=lambda t: t.valid_period.from_including)

    def get_calendar_pattern(self, pattern_id: str) -> CalendarPattern | None:
        return next((p for p in self.calendar_patterns if p.id == pattern_id), None)
