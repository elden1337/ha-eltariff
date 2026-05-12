"""DataUpdateCoordinator for the eltariff integration."""

from __future__ import annotations

import logging
import random
import zoneinfo
from datetime import UTC, date, datetime, timedelta

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
    CONF_TARIFF_NAME,
    DOMAIN,
    INFO_POLL_BASE_SECONDS,
    INFO_POLL_JITTER_SECONDS,
    SNAPSHOT_REFRESH_INTERVAL_SECONDS,
)
from .coordinator_data import EltariffCoordinatorData

_LOGGER = logging.getLogger(__name__)


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
        self._cached_info: ServerInfo | None = None
        # None means: poll immediately on first run.
        self._next_info_poll: datetime | None = None
        self._schedule_cache_key: tuple | None = None
        self._schedule_cache: list = []

    @property
    def tariff_id(self) -> str:
        return self._config_entry.data[CONF_TARIFF_ID]

    def get_cached_day_schedule(self, tariff_id: str, today: date, tz: zoneinfo.ZoneInfo) -> list:
        """Return today's tariff schedule, cached by (tariff_id, date)."""
        cache_key = (tariff_id, today)
        if cache_key != self._schedule_cache_key:
            from .api.schedule import build_day_schedule

            tariff = self.data.collection.get_tariff(tariff_id) if self.data else None
            self._schedule_cache = (
                build_day_schedule(tariff, self.data.collection, today, tz)
                if tariff is not None
                else []
            )
            self._schedule_cache_key = cache_key
        return self._schedule_cache

    @property
    def _configured_tariff_name(self) -> str | None:
        tariff_name = self._config_entry.data.get(CONF_TARIFF_NAME)
        if tariff_name:
            return tariff_name
        # Backwards compatibility for existing entries created before tariff_name was stored.
        if " — " in self._config_entry.title:
            return self._config_entry.title.split(" — ", 1)[1].strip()
        return None

    def _build_client(self) -> TariffApiClient:
        session = async_get_clientsession(self.hass)
        return TariffApiClient(
            base_url=self._config_entry.data[CONF_BASE_URL],
            session=session,
            bearer_token=(
                self._config_entry.options.get(CONF_BEARER_TOKEN)
                or self._config_entry.data.get(CONF_BEARER_TOKEN)
            ),
        )

    def _next_randomized_poll(self) -> datetime:
        """Return a future timestamp for the next /info poll, with random jitter."""
        jitter = random.uniform(-INFO_POLL_JITTER_SECONDS, INFO_POLL_JITTER_SECONDS)
        delta = timedelta(seconds=INFO_POLL_BASE_SECONDS + jitter)
        next_poll = datetime.now(tz=UTC) + delta
        _LOGGER.debug(
            "Next /info poll scheduled in %.0f s (at %s)",
            delta.total_seconds(),
            next_poll.isoformat(),
        )
        return next_poll

    async def _async_update_data(self) -> EltariffCoordinatorData:
        if self._client is None:
            self._client = self._build_client()

        now = datetime.now(tz=UTC)

        if self._next_info_poll is None or now >= self._next_info_poll:
            try:
                info = await self._client.get_info()
            except TariffApiAuthError as exc:
                raise UpdateFailed(f"Authentication error: {exc}") from exc
            except TariffApiError as exc:
                raise UpdateFailed(f"API error fetching /info: {exc}") from exc

            self._cached_info = info
            self._next_info_poll = self._next_randomized_poll()

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
        else:
            _LOGGER.debug("Skipping /info poll — next poll at %s", self._next_info_poll.isoformat())
            info = self._cached_info  # type: ignore[assignment]

        now = datetime.now(tz=UTC)
        collection = self._cached_collection
        tariff = collection.get_tariff(self.tariff_id)
        if tariff is None:
            tariff_name = self._configured_tariff_name
            if tariff_name:
                tariff = collection.find_tariff_by_name(tariff_name, at=now)

            if tariff is None:
                raise UpdateFailed(
                    f"Configured tariff {self.tariff_id!r} not found in API response"
                )

            message = (
                "Configured tariff id %s is no longer available (possibly expired); "
                "auto-switched to %s (%s) and continuing updates"
            )
            _LOGGER.warning(message, self.tariff_id, tariff.id, tariff.name)
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data={
                    **self._config_entry.data,
                    CONF_TARIFF_ID: tariff.id,
                    CONF_TARIFF_NAME: tariff.name,
                },
            )

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
