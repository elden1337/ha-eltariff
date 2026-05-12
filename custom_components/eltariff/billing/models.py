"""Data models for the billing / cost-tracking layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PeakRecord:
    """A single recorded peak: timestamp and energy value (kWh for the window)."""

    dt: datetime
    value: float  # kWh consumed during the peak_duration window

    def to_dict(self) -> dict:
        return {"dt": self.dt.isoformat(), "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> PeakRecord:
        return cls(dt=datetime.fromisoformat(d["dt"]), value=float(d["value"]))


@dataclass
class CostBreakdown:
    """Running cost breakdown for the current billing period."""

    peak_cost: float = 0.0
    transmission_cost: float = 0.0
    tax_cost: float = 0.0
    fixed_cost: float = 0.0

    observed_peak_kwh: float = 0.0
    charged_peak_kwh: float = 0.0
    # Duration of the peak measurement window in hours, used to convert kWh → kW.
    peak_duration_hours: float = 1.0
    stored_peaks: list[PeakRecord] = field(default_factory=list)
    total_energy_kwh: float = 0.0

    billing_period_start: datetime | None = None
    billing_period_end: datetime | None = None
    currency: str = "SEK"

    @property
    def total(self) -> float:
        return self.peak_cost + self.transmission_cost + self.tax_cost + self.fixed_cost

    @property
    def observed_peak_kw(self) -> float:
        return self.observed_peak_kwh / self.peak_duration_hours if self.peak_duration_hours > 0 else 0.0

    @property
    def charged_peak_kw(self) -> float:
        return self.charged_peak_kwh / self.peak_duration_hours if self.peak_duration_hours > 0 else 0.0


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
    total_energy_kwh: float = 0.0

    def to_dict(self) -> dict:
        return {
            "billing_period_start": self.billing_period_start_iso,
            "peaks": [p.to_dict() for p in self.peaks],
            "window_start": self.current_window_start_iso,
            "window_start_reading": self.current_window_start_reading,
            "window_peak": self.current_window_peak,
            "prev_reading": self.prev_reading,
            "acc_transmission": self.accumulated_transmission_cost,
            "acc_tax": self.accumulated_tax_cost,
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
            total_energy_kwh=float(d.get("total_energy_kwh", 0.0)),
        )
