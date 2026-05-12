"""Peak tracking for the billing service.

Stores the top *N* peaks across the billing period (one per identification
period) and computes observed / charged peak values.
"""
from __future__ import annotations

import logging
from datetime import datetime

from .iso_duration import ParsedDuration, is_same_period
from .models import PeakRecord

_LOGGER = logging.getLogger(__name__)


class PeakTracker:
    """Track energy peaks across a billing period.

    Parameters
    ----------
    identification_period:
        Only one peak per identification period is stored (the highest).
        E.g. ``P1D`` means one peak per calendar day.
    number_of_peaks:
        Maximum number of peaks to keep (the top N).
    peak_function:
        How to derive the charged peak from stored peaks.
        ``"average"`` (default), ``"maximum"``, ``"minimum"``.
    """

    def __init__(
        self,
        identification_period: ParsedDuration,
        number_of_peaks: int,
        peak_function: str = "average",
    ) -> None:
        self._id_period = identification_period
        self._number_of_peaks = max(number_of_peaks, 1)
        self._peak_function = (peak_function or "average").lower()
        self._peaks: list[PeakRecord] = []

    @property
    def peaks(self) -> list[PeakRecord]:
        return list(self._peaks)

    @property
    def observed_peak(self) -> float:
        """The observed (minimum stored) peak value.

        Represents the lowest bar the customer has already committed to.
        Returns 0.0 if no peaks are stored.
        """
        if not self._peaks:
            return 0.0
        return min(p.value for p in self._peaks)

    @property
    def charged_peak(self) -> float:
        """The charged peak value used for billing.

        Depends on peak_function:
        - average: sum / min(len, number_of_peaks)
        - maximum: max of stored peaks
        - minimum: min of stored peaks
        """
        if not self._peaks:
            return 0.0

        values = [p.value for p in self._peaks]

        if self._peak_function == "maximum":
            return max(values)
        if self._peak_function == "minimum":
            return min(values)

        # Default: average
        divider = min(len(values), self._number_of_peaks)
        return sum(values) / divider if divider > 0 else 0.0

    def try_add_peak(self, dt: datetime, value: float) -> bool:
        """Try to add a peak value.

        Rules (mirroring peaq-site logic):
        1. If a peak already exists in the same identification period,
           replace it only if the new value is higher.
        2. If we're below the max peak count, add directly.
        3. If at capacity, replace the smallest peak if the new value is higher.

        Returns True if the peak was added/updated.
        """
        if value <= 0:
            return False

        # Check for existing peak in the same identification period
        same_period_idx = next(
            (
                i
                for i, p in enumerate(self._peaks)
                if is_same_period(dt, p.dt, self._id_period)
            ),
            None,
        )

        if same_period_idx is not None:
            if value > self._peaks[same_period_idx].value:
                self._peaks[same_period_idx] = PeakRecord(dt=dt, value=value)
                _LOGGER.debug(
                    "Updated peak in same period: %.3f kWh at %s", value, dt
                )
                return True
            return False

        # Under capacity: add directly
        if len(self._peaks) < self._number_of_peaks:
            self._peaks.append(PeakRecord(dt=dt, value=value))
            _LOGGER.debug("Added new peak: %.3f kWh at %s", value, dt)
            return True

        # At capacity: replace the minimum if higher
        min_idx = min(range(len(self._peaks)), key=lambda i: self._peaks[i].value)
        if value > self._peaks[min_idx].value:
            _LOGGER.debug(
                "Replaced min peak (%.3f) with %.3f kWh at %s",
                self._peaks[min_idx].value,
                value,
                dt,
            )
            self._peaks[min_idx] = PeakRecord(dt=dt, value=value)
            return True

        return False

    def reset(self) -> None:
        """Clear all peaks (new billing period)."""
        self._peaks.clear()

    def restore(self, records: list[PeakRecord]) -> None:
        """Restore peaks from a list of PeakRecord instances."""
        self._peaks.clear()
        self._peaks.extend(records)

    def serialise(self) -> list[PeakRecord]:
        """Return a snapshot of stored peaks."""
        return list(self._peaks)
