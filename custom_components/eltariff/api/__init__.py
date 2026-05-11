"""API package for the eltariff integration."""
from .client import TariffApiAuthError, TariffApiClient, TariffApiError
from .models import (
    ActiveTariffSnapshot,
    CalendarPattern,
    CalendarPatternType,
    ComponentType,
    Price,
    PriceComponent,
    PriceGroup,
    ScheduleSlot,
    ServerInfo,
    Tariff,
    TariffCollection,
    ValidPeriod,
)
from .schedule import (
    build_day_schedule,
    next_transition_at,
    resolve_active_components,
)

__all__ = [
    "ActiveTariffSnapshot",
    "CalendarPattern",
    "CalendarPatternType",
    "ComponentType",
    "Price",
    "PriceComponent",
    "PriceGroup",
    "ScheduleSlot",
    "ServerInfo",
    "Tariff",
    "TariffApiAuthError",
    "TariffApiClient",
    "TariffApiError",
    "TariffCollection",
    "ValidPeriod",
    "build_day_schedule",
    "next_transition_at",
    "resolve_active_components",
]
