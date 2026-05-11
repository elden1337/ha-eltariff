"""Constants for the eltariff integration."""
DOMAIN = "eltariff"

DEFAULT_BASE_URL = "https://api.goteborgenergi.cloud/gridtariff/v0"

CONF_BASE_URL = "base_url"
CONF_TARIFF_ID = "tariff_id"
CONF_VAT_MODE = "vat_mode"
CONF_BEARER_TOKEN = "bearer_token"

VAT_MODE_INC = "inc_vat"
VAT_MODE_EX = "ex_vat"
VAT_MODES = [VAT_MODE_INC, VAT_MODE_EX]

# How often to poll /info to check tariffDataLastUpdated
INFO_POLL_INTERVAL_SECONDS = 3600  # 1 hour

# How often the coordinator recomputes the active snapshot from cached data
SNAPSHOT_REFRESH_INTERVAL_SECONDS = 60
