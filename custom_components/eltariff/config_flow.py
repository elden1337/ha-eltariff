"""Config flow for the eltariff integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TariffApiAuthError, TariffApiClient, TariffApiError
from .const import (
    CONF_BASE_URL,
    CONF_BEARER_TOKEN,
    CONF_TARIFF_ID,
    CONF_VAT_MODE,
    DEFAULT_BASE_URL,
    DOMAIN,
    VAT_MODE_INC,
    VAT_MODES,
)

_LOGGER = logging.getLogger(__name__)


class EltariffConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._base_url: str = DEFAULT_BASE_URL
        self._bearer_token: str | None = None
        self._available_tariffs: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._base_url = user_input[CONF_BASE_URL].rstrip("/")
            self._bearer_token = user_input.get(CONF_BEARER_TOKEN) or None

            try:
                session = async_get_clientsession(self.hass)
                client = TariffApiClient(self._base_url, session, self._bearer_token)
                collection = await client.get_tariffs()
                self._available_tariffs = [
                    {"id": t.id, "label": f"{t.name} ({t.product})"}
                    for t in collection.tariffs
                ]
            except TariffApiAuthError:
                errors["base"] = "auth_error"
            except TariffApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error in config flow step_user")
                errors["base"] = "unknown"

            if not errors:
                return await self.async_step_tariff()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                vol.Optional(CONF_BEARER_TOKEN): str,
            }),
            errors=errors,
        )

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            tariff_id = user_input[CONF_TARIFF_ID]
            vat_mode = user_input[CONF_VAT_MODE]

            await self.async_set_unique_id(f"{self._base_url}_{tariff_id}")
            self._abort_if_unique_id_configured()

            tariff_label = next(
                (t["label"] for t in self._available_tariffs if t["id"] == tariff_id),
                tariff_id,
            )

            return self.async_create_entry(
                title=tariff_label,
                data={
                    CONF_BASE_URL: self._base_url,
                    CONF_TARIFF_ID: tariff_id,
                    CONF_VAT_MODE: vat_mode,
                    CONF_BEARER_TOKEN: self._bearer_token,
                },
            )

        tariff_options = {t["id"]: t["label"] for t in self._available_tariffs}

        return self.async_show_form(
            step_id="tariff",
            data_schema=vol.Schema({
                vol.Required(CONF_TARIFF_ID): vol.In(tariff_options),
                vol.Required(CONF_VAT_MODE, default=VAT_MODE_INC): vol.In(VAT_MODES),
            }),
            errors=errors,
        )
