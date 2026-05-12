"""PeakIdentificationSettings dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PeakIdentificationSettings:
    number_of_peaks_for_average: int | None = None
    peak_function: str | None = None
    # ISO 8601 duration strings (e.g. "PT15M", "PT1H", "P1M")
    peak_identification_period: str | None = None
    peak_duration: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PeakIdentificationSettings:
        raw = d.get("numberOfPeaksForAverageCalculation")
        return cls(
            number_of_peaks_for_average=int(raw) if raw is not None else None,
            peak_function=d.get("peakFunction"),
            peak_identification_period=d.get("peakIdentificationPeriod"),
            peak_duration=d.get("peakDuration"),
        )
