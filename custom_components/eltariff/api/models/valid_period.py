"""ValidPeriod dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
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
