"""Constants for the Fluvigil integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "fluvigil"

CONF_STATION_ID: Final = "station_id"
CONF_STATION_NAME: Final = "station_name"

DEFAULT_BASE_URL: Final = "https://fluvigil.de"

# The upstream sources publish on a 15-minute raster and Fluvigil's own sweep follows it, so
# a gauge value cannot change in between. Polling faster would fetch the same number twice.
# Decided in docs/home-assistant-integration-decisions.md in the service repository.
UPDATE_INTERVAL: Final = timedelta(minutes=15)

# One request should never hold the coordinator hostage; the next cycle is 15 minutes away.
REQUEST_TIMEOUT_SECONDS: Final = 30
