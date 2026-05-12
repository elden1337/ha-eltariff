"""ComponentType enumeration."""
from __future__ import annotations

from enum import StrEnum


class ComponentType(StrEnum):
    FIXED = "fixed"
    PEAK = "peak"
    ENERGY = "energy"
