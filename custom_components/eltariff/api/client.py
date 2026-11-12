"""Async HTTP client for the RI-SE Grid Tariff API."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp

from .errors import TariffApiAuthError, TariffApiError
from .models import ServerInfo, Tariff, TariffCollection
from .models.prices_response import PricesResponse

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)


class TariffApiClient:
    """Thin async wrapper around the RI-SE Grid Tariff OpenAPI endpoints."""

    def __init__(
        self,
        base_url: str,
        session: aiohttp.ClientSession,
        bearer_token: str | None = None,
        *,
        auth_header: str = "Authorization",
        auth_scheme: str | None = "Bearer",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._bearer_token = bearer_token
        # Some DSOs (e.g. Azure API Management gateways) expect the API key in a
        # custom header with no scheme prefix instead of a standard Bearer token.
        self._auth_header = auth_header
        self._auth_scheme = auth_scheme

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._bearer_token:
            value = (
                f"{self._auth_scheme} {self._bearer_token}"
                if self._auth_scheme
                else self._bearer_token
            )
            headers[self._auth_header] = value
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

    async def get_prices(
        self,
        component_id: str,
        target_date: date | None = None,
        url: str | None = None,
        *,
        from_including: datetime | None = None,
        to_excluding: datetime | None = None,
    ) -> PricesResponse:
        """Fetch hourly price curve.

        Uses the component's own ``url`` (e.g. ``/prices?product=GN6KWST``) when
        given, otherwise uses ``/prices?componentId=...``.
        """
        path = url or f"/prices?{urlencode({'componentId': component_id})}"
        parts = urlsplit(path)
        query = parse_qsl(parts.query)
        if target_date is not None:
            query.append(("date", target_date.isoformat()))
        if from_including is not None:
            query.append(("fromIncluding", from_including.isoformat()))
        if to_excluding is not None:
            query.append(("toExcluding", to_excluding.isoformat()))
        path = urlunsplit(parts._replace(query=urlencode(query)))
        data = await self._get(path)
        return PricesResponse.from_dict(data)
