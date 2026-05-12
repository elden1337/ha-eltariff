"""Async HTTP client for the RI-SE Grid Tariff API."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .errors import TariffApiAuthError, TariffApiError
from .models import ServerInfo, Tariff, TariffCollection

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)


class TariffApiClient:
    """Thin async wrapper around the RI-SE Grid Tariff OpenAPI endpoints."""

    def __init__(
        self,
        base_url: str,
        session: aiohttp.ClientSession,
        bearer_token: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._bearer_token = bearer_token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    async def _get(self, path: str) -> Any:
        url = f"{self._base_url}{path}"
        try:
            async with self._session.get(
                url, headers=self._headers(), timeout=DEFAULT_TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise TariffApiAuthError(f"Auth error {resp.status} from {url}")
                resp.raise_for_status()
                return await resp.json()
        except TariffApiAuthError:
            raise
        except aiohttp.ClientError as exc:
            raise TariffApiError(f"HTTP error fetching {url}: {exc}") from exc

    async def get_info(self) -> ServerInfo:
        data = await self._get("/info")
        return ServerInfo.from_dict(data)

    async def get_tariffs(self) -> TariffCollection:
        data = await self._get("/tariffs")
        return TariffCollection.from_dict(data)

    async def get_tariff(self, tariff_id: str) -> tuple[Tariff, TariffCollection]:
        """Return a single tariff together with its calendar patterns."""
        data = await self._get(f"/tariffs/{tariff_id}")
        collection = TariffCollection.from_dict(data)
        tariff = collection.get_tariff(tariff_id)
        if tariff is None:
            raise TariffApiError(f"Tariff {tariff_id!r} not found in response")
        return tariff, collection
