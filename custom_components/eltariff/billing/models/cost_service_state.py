from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .peak_record import PeakRecord

_LOGGER = logging.getLogger(__name__)


def _parse_peaks(raw: object) -> list[PeakRecord]:
    """Parse stored peaks, skipping any malformed entries."""
    if not isinstance(raw, list):
        return []
    peaks: list[PeakRecord] = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        try:
            peaks.append(PeakRecord.from_dict(p))
        except (KeyError, TypeError, ValueError):
            _LOGGER.warning("Skipping malformed stored peak: %r", p)
    return peaks


@dataclass
class CostServiceState:
    """Serialisable snapshot of the cost service's internal state.

    Persisted via RestoreEntity so accumulated costs and peaks survive HA restarts.
    """

    billing_period_start_iso: str | None = None
    peaks: list[PeakRecord] = field(default_factory=list)
    current_window_start_iso: str | None = None
    current_window_start_reading: float | None = None
    current_window_peak: float = 0.0
    prev_reading: float | None = None
    accumulated_transmission_cost: float = 0.0
    accumulated_tax_cost: float = 0.0
    accumulated_price_curve_cost: float = 0.0
    total_energy_kwh: float = 0.0

    def to_dict(self) -> dict:
        return {
            "billing_period_start": self.billing_period_start_iso,
            "peaks": [p.to_dict() for p in self.peaks if hasattr(p, 'to_dict')],
            "window_start": self.current_window_start_iso,
            "window_start_reading": self.current_window_start_reading,
            "window_peak": self.current_window_peak,
            "prev_reading": self.prev_reading,
            "acc_transmission": self.accumulated_transmission_cost,
            "acc_tax": self.accumulated_tax_cost,
            "acc_price_curve": self.accumulated_price_curve_cost,
            "total_energy_kwh": self.total_energy_kwh,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CostServiceState:
        return cls(
            billing_period_start_iso=d.get("billing_period_start"),
            peaks=_parse_peaks(d.get("peaks")),
            current_window_start_iso=d.get("window_start"),
            current_window_start_reading=d.get("window_start_reading"),
            current_window_peak=float(d.get("window_peak", 0.0)),
            prev_reading=d.get("prev_reading"),
            accumulated_transmission_cost=float(d.get("acc_transmission", 0.0)),
            accumulated_tax_cost=float(d.get("acc_tax", 0.0)),
            accumulated_price_curve_cost=float(d.get("acc_price_curve", 0.0)),
            total_energy_kwh=float(d.get("total_energy_kwh", 0.0)),
        )
