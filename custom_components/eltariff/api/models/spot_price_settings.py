"""SpotPriceSettings dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SpotPriceSettings:
    multiplier: float
    currency: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SpotPriceSettings:
        return cls(
            multiplier=float(d["multiplier"]),
            currency=d["currency"],
        )
