"""Public re-exports for backwards compatibility.

Any import that previously used ``from .api.models import X`` or
``from custom_components.eltariff.api.models import X`` will still work.
"""
from .price import (
    ComponentType,
    Price,
    PriceComponent,
    PriceGroup,
)
from .schedule import (
    ActivePeriod,
    CalendarPattern,
    CalendarPatternReferences,
    CalendarPatternType,
    PeakIdentificationSettings,
    RecurringPeriod,
    ValidPeriod,
)
from .server import ServerInfo
from .snapshot import ActiveTariffSnapshot, ScheduleSlot
from .tariff import Tariff, TariffCollection

__all__ = [
    "ActivePeriod",
    "ActiveTariffSnapshot",
    "CalendarPattern",
    "CalendarPatternReferences",
    "CalendarPatternType",
    "ComponentType",
    "PeakIdentificationSettings",
    "Price",
    "PriceComponent",
    "PriceGroup",
    "RecurringPeriod",
    "ScheduleSlot",
    "ServerInfo",
    "Tariff",
    "TariffCollection",
    "ValidPeriod",
]
