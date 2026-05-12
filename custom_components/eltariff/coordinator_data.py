"""EltariffCoordinatorData dataclass."""

from __future__ import annotations

from datetime import datetime

from .api import ActiveTariffSnapshot, ServerInfo, TariffCollection


class EltariffCoordinatorData:
    """All data the coordinator exposes to entities."""

    def __init__(
        self,
        info: ServerInfo,
        collection: TariffCollection,
        snapshot: ActiveTariffSnapshot,
        next_transition: datetime | None,
    ) -> None:
        self.info = info
        self.collection = collection
        self.snapshot = snapshot
        self.next_transition = next_transition
