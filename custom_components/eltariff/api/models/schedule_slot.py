"""ScheduleSlot dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ScheduleSlot:
    """One contiguous time band in a day schedule."""

    start: datetime
    end: datetime
    band_reference: str
    price_inc_vat: float
    price_ex_vat: float
    currency: str
