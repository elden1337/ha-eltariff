"""EltariffCoordinatorData dataclass."""

from __future__ import annotations

from datetime import datetime

from .api import ActiveTariffSnapshot, ServerInfo, TariffCollection
from .api.models.prices_response import PricesResponse


class EltariffCoordinatorData:
    """All data the coordinator exposes to entities."""

    def __init__(
        self,
        info: ServerInfo,
        collection: TariffCollection,
        snapshot: ActiveTariffSnapshot,
        next_transition: datetime | None,
        price_curves: dict[str, PricesResponse] | None = None,
    ) -> None:
        self.info = info
        self.collection = collection
        self.snapshot = snapshot
        self.next_transition = next_transition
        self.price_curves = price_curves or {}
