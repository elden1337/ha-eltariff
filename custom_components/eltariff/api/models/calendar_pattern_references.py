"""CalendarPatternReferences dataclass."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CalendarPatternReferences:
    include: list[str]
    exclude: list[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalendarPatternReferences:
        return cls(
            include=list(d.get("include", [])),
            exclude=list(d.get("exclude", [])),
        )
