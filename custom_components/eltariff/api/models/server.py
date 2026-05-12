"""Server-related dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ServerInfo:
    timezone: str
    tariff_data_last_updated: datetime | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ServerInfo:
        raw_ts = d.get("tariffDataLastUpdated")
        return cls(
            timezone=d.get("timezone", "Europe/Stockholm"),
            tariff_data_last_updated=datetime.fromisoformat(raw_ts) if raw_ts else None,
        )
