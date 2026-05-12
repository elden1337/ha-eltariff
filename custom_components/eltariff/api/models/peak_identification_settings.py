"""PeakIdentificationSettings dataclass."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PeakIdentificationSettings:
    number_of_peaks_for_average: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PeakIdentificationSettings:
        return cls(
            number_of_peaks_for_average=int(d["numberOfPeaksForAverageCalculation"])
        )
