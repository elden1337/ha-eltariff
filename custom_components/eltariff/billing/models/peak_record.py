from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PeakRecord:
    """A single recorded peak: timestamp and energy value (kWh for the window)."""

    dt: datetime
    value: float  # kWh consumed during the peak window
    component_id: str = ""  # power component active when the peak was recorded

    def to_dict(self) -> dict:
        return {"dt": self.dt.isoformat(), "value": self.value, "component_id": self.component_id}

    @classmethod
    def from_dict(cls, d: dict) -> PeakRecord:
        return cls(
            dt=datetime.fromisoformat(d["dt"]),
            value=float(d["value"]),
            component_id=d.get("component_id", ""),
        )
