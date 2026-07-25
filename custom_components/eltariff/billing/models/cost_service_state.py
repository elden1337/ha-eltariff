from __future__ import annotations

from dataclasses import dataclass, field

from .peak_record import PeakRecord


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
            peaks=[PeakRecord.from_dict(p) for p in d.get("peaks", []) if isinstance(p, dict)],
            current_window_start_iso=d.get("window_start"),
            current_window_start_reading=d.get("window_start_reading"),
            current_window_peak=float(d.get("window_peak", 0.0)),
            prev_reading=d.get("prev_reading"),
            accumulated_transmission_cost=float(d.get("acc_transmission", 0.0)),
            accumulated_tax_cost=float(d.get("acc_tax", 0.0)),
            accumulated_price_curve_cost=float(d.get("acc_price_curve", 0.0)),
            total_energy_kwh=float(d.get("total_energy_kwh", 0.0)),
        )
