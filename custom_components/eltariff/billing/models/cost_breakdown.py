from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .peak_record import PeakRecord


@dataclass
class CostBreakdown:
    """Running cost breakdown for the current billing period."""

    peak_cost: float = 0.0
    transmission_cost: float = 0.0
    tax_cost: float = 0.0
    fixed_cost: float = 0.0
    price_curve_cost: float = 0.0

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
        return (
            self.peak_cost
            + self.transmission_cost
            + self.tax_cost
            + self.fixed_cost
            + self.price_curve_cost
        )

    @property
    def observed_peak_kw(self) -> float:
        return (
            self.observed_peak_kwh / self.peak_duration_hours
            if self.peak_duration_hours > 0
            else 0.0
        )

    @property
    def charged_peak_kw(self) -> float:
        return (
            self.charged_peak_kwh / self.peak_duration_hours
            if self.peak_duration_hours > 0
            else 0.0
        )
