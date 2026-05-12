"""Constants for the eltariff integration."""
DOMAIN = "eltariff"

DEFAULT_BASE_URL = "https://api.goteborgenergi.cloud/gridtariff/v0"

CONF_BASE_URL = "base_url"
CONF_TARIFF_ID = "tariff_id"
CONF_TARIFF_NAME = "tariff_name"
CONF_VAT_MODE = "vat_mode"
CONF_BEARER_TOKEN = "bearer_token"
CONF_DSO_KEY = "dso_key"

KNOWN_DSOS: dict[str, dict[str, str]] = {
    "goteborg_energi": {
        "name": "Göteborg Energi Nät AB",
        "base_url": "https://api.goteborgenergi.cloud/gridtariff/v0",
    },
    "tekniska_verken": {
        "name": "Tekniska Verken",
        "base_url": "https://api.tekniskaverken.net/subscription/public/v0",
    },
    "norrtalje_energi": {
        "name": "Norrtälje Energi AB",
        "base_url": "https://www.norrtaljeenergi.se/api",
    },
    "skanska_energi": {
        "name": "Skånska Energi Nät AB",
        # /tariffs is part of the base path for this DSO's API
        "base_url": "https://apim.kraftringen.se/customer/SKN/tariffs",
    },
    "kraftringen_nat": {
        "name": "Kraftringen Nät AB",
        # /tariffs is part of the base path for this DSO's API
        "base_url": "https://apim.kraftringen.se/customer/tariffs",
    },
    "custom": {
        "name": "Custom URL",
        "base_url": "",
    },
}

VAT_MODE_INC = "inc_vat"
VAT_MODE_EX = "ex_vat"
VAT_MODES = [VAT_MODE_INC, VAT_MODE_EX]

# How often to poll /info to check tariffDataLastUpdated (base interval, before jitter)
INFO_POLL_BASE_SECONDS = 12 * 3600  # ~12 hours

# Random jitter applied to INFO_POLL_BASE_SECONDS (uniform ±).
# Spreads requests across installations so the API isn't hit simultaneously.
INFO_POLL_JITTER_SECONDS = 30 * 60  # ±30 minutes

# How often the coordinator recomputes the active snapshot from cached data.
# Kept short so tariff period transitions (peak → off-peak etc.) are reflected promptly.
SNAPSHOT_REFRESH_INTERVAL_SECONDS = 60
