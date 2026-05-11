"""DataUpdateCoordinator for the eltariff integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    ActiveTariffSnapshot,
    ServerInfo,
    TariffCollection,
    next_transition_at,
    resolve_active_components,
)
from .api.client import TariffApiAuthError, TariffApiClient, TariffApiError
from .const import (
    CONF_BASE_URL,
    CONF_BEARER_TOKEN,
    CONF_TARIFF_ID,
    DOMAIN,
    SNAPSHOT_REFRESH_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


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


class EltariffCoordinator(DataUpdateCoordinator[EltariffCoordinatorData]):
    """Coordinator that separates slow network fetches from fast snapshot recomputation."""

    def __init__(self, hass: HomeAssistant, config_entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SNAPSHOT_REFRESH_INTERVAL_SECONDS),
        )
        self._config_entry = config_entry
        self._client: TariffApiClient | None = None
        self._cached_collection: TariffCollection | None = None
        self._cached_last_updated: datetime | None = None

    @property
    def tariff_id(self) -> str:
        return self._config_entry.data[CONF_TARIFF_ID]

    def _build_client(self) -> TariffApiClient:
        session = async_get_clientsession(self.hass)
        return TariffApiClient(
            base_url=self._config_entry.data[CONF_BASE_URL],
            session=session,
            bearer_token=self._config_entry.data.get(CONF_BEARER_TOKEN),
        )

    async def _async_update_data(self) -> EltariffCoordinatorData:
        if self._client is None:
            self._client = self._build_client()

        try:
            info = await self._client.get_info()
        except TariffApiAuthError as exc:
            raise UpdateFailed(f"Authentication error: {exc}") from exc
        except TariffApiError as exc:
            raise UpdateFailed(f"API error fetching /info: {exc}") from exc

        if (
            self._cached_collection is None
            or info.tariff_data_last_updated != self._cached_last_updated
        ):
            _LOGGER.debug(
                "Tariff data changed (was %s, now %s) — fetching full collection",
                self._cached_last_updated,
                info.tariff_data_last_updated,
            )
            try:
                self._cached_collection = await self._client.get_tariffs()
                self._cached_last_updated = info.tariff_data_last_updated
            except TariffApiError as exc:
                raise UpdateFailed(f"API error fetching /tariffs: {exc}") from exc

        collection = self._cached_collection
        tariff = collection.get_tariff(self.tariff_id)
        if tariff is None:
            raise UpdateFailed(
                f"Configured tariff {self.tariff_id!r} not found in API response"
            )

        now = datetime.now(tz=timezone.utc)
        snapshot = resolve_active_components(tariff, collection, now)

        if snapshot.parse_warnings:
            for warning in snapshot.parse_warnings:
                _LOGGER.warning("Schedule resolution: %s", warning)

        transition = next_transition_at(tariff, collection, now)

        return EltariffCoordinatorData(
            info=info,
            collection=collection,
            snapshot=snapshot,
            next_transition=transition,
        )
