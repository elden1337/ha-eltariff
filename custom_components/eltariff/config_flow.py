"""Config flow for the eltariff integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api.client import TariffApiAuthError, TariffApiClient, TariffApiError
from .const import (
    CONF_BASE_URL,
    CONF_BEARER_TOKEN,
    CONF_DSO_KEY,
    CONF_ENERGY_SENSOR,
    CONF_TARIFF_ID,
    CONF_TARIFF_NAME,
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

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> EltariffOptionsFlow:
        return EltariffOptionsFlow(config_entry)

    def _build_client(
        self, base_url: str, dso_key: str, token: str | None = None
    ) -> TariffApiClient:
        dso = KNOWN_DSOS.get(dso_key, {})
        session = async_get_clientsession(self.hass)
        return TariffApiClient(
            base_url,
            session,
            token,
            auth_header=dso.get("auth_header", "Authorization"),
            auth_scheme=dso.get("auth_scheme", "Bearer"),
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            dso_key = user_input[CONF_DSO_KEY]
            base_url = KNOWN_DSOS[dso_key]["base_url"]
            self._form_data[CONF_DSO_KEY] = dso_key
            self._form_data[CONF_BASE_URL] = base_url

            if KNOWN_DSOS[dso_key].get("requires_auth"):
                # This DSO requires credentials before /info can even be validated.
                return await self.async_step_auth()

            try:
                client = self._build_client(base_url, dso_key)
                await client.get_info()
            except TariffApiAuthError:
                errors["base"] = "auth_error"
            except TariffApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating DSO endpoint")
                errors["base"] = "unknown"

            if not errors:
                return await self.async_step_tariff()

        dso_options = {key: dso["name"] for key, dso in KNOWN_DSOS.items()}

        schema_dict: dict = {
            vol.Required(CONF_DSO_KEY): vol.In(dso_options),
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_auth(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect credentials for DSOs that require them before validating /info."""
        errors: dict[str, str] = {}
        dso_key = self._form_data[CONF_DSO_KEY]
        base_url = self._form_data[CONF_BASE_URL]

        if user_input is not None:
            token = user_input[CONF_BEARER_TOKEN]
            try:
                client = self._build_client(base_url, dso_key, token)
                await client.get_info()
            except TariffApiAuthError:
                errors["base"] = "auth_error"
            except TariffApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating DSO endpoint")
                errors["base"] = "unknown"

            if not errors:
                self._form_data[CONF_BEARER_TOKEN] = token
                return await self.async_step_tariff()

        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema({vol.Required(CONF_BEARER_TOKEN): str}),
            errors=errors,
        )

    async def async_step_tariff(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
            client = self._build_client(
                self._form_data[CONF_BASE_URL],
                self._form_data[CONF_DSO_KEY],
                self._form_data.get(CONF_BEARER_TOKEN),
            )
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

        now = dt_util.now()
        today = now.date()
        valid_tariffs = [
            t for t in collection.tariffs
            if t.valid_period.to_excluding is None or t.valid_period.to_excluding > today
        ]
        sorted_tariffs = sorted(
            valid_tariffs,
            key=lambda t: 0 if t.valid_period.contains(now) else 1,
        )

        self._available_tariffs = [
            {
                "id": t.id,
                "name": t.name,
                "valid_from": t.valid_period.from_including.isoformat(),
                "valid_to": (
                    t.valid_period.to_excluding.isoformat()
                    if t.valid_period.to_excluding is not None
                    else None
                ),
            }
            for t in sorted_tariffs
        ]

        def _label(t: dict) -> str:
            to_str = t["valid_to"] if t["valid_to"] else "present"
            return f"{t['name']} ({t['valid_from']} – {to_str})"

        tariff_options = {t["id"]: _label(t) for t in self._available_tariffs}

        return self.async_show_form(
            step_id="tariff",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TARIFF_ID): vol.In(tariff_options),
                }
            ),
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
                    CONF_TARIFF_NAME: tariff_name,
                    CONF_VAT_MODE: user_input[CONF_VAT_MODE],
                    CONF_BEARER_TOKEN: (
                        user_input.get(CONF_BEARER_TOKEN)
                        or self._form_data.get(CONF_BEARER_TOKEN)
                    ),
                    CONF_ENERGY_SENSOR: user_input.get(CONF_ENERGY_SENSOR) or None,
                },
            )

        return self.async_show_form(
            step_id="options",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_VAT_MODE, default=VAT_MODE_INC): vol.In(VAT_MODES),
                        vol.Optional(CONF_BEARER_TOKEN): str,
                        vol.Optional(CONF_ENERGY_SENSOR): selector.EntitySelector(
                            selector.EntitySelectorConfig(domain="sensor")
                        ),
                    }
                ),
                {CONF_BEARER_TOKEN: self._form_data.get(CONF_BEARER_TOKEN)},
            ),
            errors={},
        )


class EltariffOptionsFlow(config_entries.OptionsFlow):
    """Options flow — allows reconfiguring VAT mode, bearer token, and energy sensor."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_VAT_MODE: user_input[CONF_VAT_MODE],
                    CONF_BEARER_TOKEN: user_input.get(CONF_BEARER_TOKEN) or None,
                    CONF_ENERGY_SENSOR: user_input.get(CONF_ENERGY_SENSOR) or None,
                },
            )

        current_vat = self._entry.options.get(CONF_VAT_MODE) or self._entry.data.get(
            CONF_VAT_MODE, VAT_MODE_INC
        )
        current_token = (
            self._entry.options.get(CONF_BEARER_TOKEN)
            or self._entry.data.get(CONF_BEARER_TOKEN)
            or ""
        )
        current_entity = (
            self._entry.options.get(CONF_ENERGY_SENSOR)
            or self._entry.data.get(CONF_ENERGY_SENSOR)
            or ""
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_VAT_MODE): vol.In(VAT_MODES),
                vol.Optional(CONF_BEARER_TOKEN): str,
                vol.Optional(CONF_ENERGY_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_VAT_MODE: current_vat,
                    CONF_BEARER_TOKEN: current_token,
                    CONF_ENERGY_SENSOR: current_entity,
                },
            ),
            errors={},
        )
