"""Config flow for the eltariff integration."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.client import TariffApiAuthError, TariffApiClient, TariffApiError
from .const import (
    CONF_BASE_URL,
    CONF_BEARER_TOKEN,
    CONF_DSO_KEY,
    CONF_TARIFF_ID,
    CONF_VAT_MODE,
    DOMAIN,
    KNOWN_DSOS,
    VAT_MODE_INC,
    VAT_MODES,
)

_LOGGER = logging.getLogger(__name__)


class EltariffConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._form_data: dict[str, Any] = {}
        self._available_tariffs: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            dso_key = user_input[CONF_DSO_KEY]
            if dso_key == "custom":
                base_url = user_input.get(CONF_BASE_URL, "").rstrip("/")
                if not base_url:
                    errors[CONF_BASE_URL] = "invalid_url"
            else:
                base_url = KNOWN_DSOS[dso_key]["base_url"]

            if not errors:
                try:
                    session = async_get_clientsession(self.hass)
                    client = TariffApiClient(base_url, session, None)
                    await client.get_info()
                except TariffApiAuthError:
                    errors["base"] = "auth_error"
                except TariffApiError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error validating DSO endpoint")
                    errors["base"] = "unknown"

            if not errors:
                self._form_data[CONF_DSO_KEY] = dso_key
                self._form_data[CONF_BASE_URL] = base_url
                return await self.async_step_tariff()

        dso_options = {key: dso["name"] for key, dso in KNOWN_DSOS.items()}

        schema_dict: dict = {
            vol.Required(CONF_DSO_KEY): vol.In(dso_options),
            vol.Optional(CONF_BASE_URL): str,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            tariff_id = user_input[CONF_TARIFF_ID]
            tariff_name = next(
                (t["name"] for t in self._available_tariffs if t["id"] == tariff_id),
                tariff_id,
            )
            self._form_data[CONF_TARIFF_ID] = tariff_id
            self._form_data["_tariff_name"] = tariff_name
            return await self.async_step_options()

        try:
            session = async_get_clientsession(self.hass)
            client = TariffApiClient(self._form_data[CONF_BASE_URL], session, None)
            collection = await client.get_tariffs()
        except TariffApiAuthError:
            errors["base"] = "auth_error"
            return self.async_show_form(
                step_id="tariff",
                data_schema=vol.Schema({}),
                errors=errors,
            )
        except TariffApiError:
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="tariff",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        now = datetime.now(tz=timezone.utc)
        sorted_tariffs = sorted(
            collection.tariffs,
            key=lambda t: (0 if t.valid_period.contains(now) else 1),
        )

        self._available_tariffs = [{"id": t.id, "name": t.name} for t in sorted_tariffs]
        tariff_options = {t["id"]: t["name"] for t in self._available_tariffs}

        return self.async_show_form(
            step_id="tariff",
            data_schema=vol.Schema({
                vol.Required(CONF_TARIFF_ID): vol.In(tariff_options),
            }),
            errors=errors,
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            dso_key = self._form_data[CONF_DSO_KEY]
            dso_name = KNOWN_DSOS.get(dso_key, {}).get("name", dso_key)
            tariff_name = self._form_data.pop("_tariff_name", self._form_data[CONF_TARIFF_ID])

            await self.async_set_unique_id(
                f"{self._form_data[CONF_BASE_URL]}_{self._form_data[CONF_TARIFF_ID]}"
            )
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"{dso_name} — {tariff_name}",
                data={
                    **self._form_data,
                    CONF_VAT_MODE: user_input[CONF_VAT_MODE],
                    CONF_BEARER_TOKEN: user_input.get(CONF_BEARER_TOKEN) or None,
                },
            )

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema({
                vol.Required(CONF_VAT_MODE, default=VAT_MODE_INC): vol.In(VAT_MODES),
                vol.Optional(CONF_BEARER_TOKEN): str,
            }),
            errors={},
        )
