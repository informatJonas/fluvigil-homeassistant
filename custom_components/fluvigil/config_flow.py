"""Setup dialog: an API key, then one gauge."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import (
    FluvigilAuthError,
    FluvigilClient,
    FluvigilError,
    FluvigilRateLimitError,
    StationSummary,
)
from .const import CONF_STATION_ID, CONF_STATION_NAME, DEFAULT_BASE_URL, DOMAIN

CONF_SEARCH = "search"


class FluvigilConfigFlow(ConfigFlow, domain=DOMAIN):
    """Key first, gauge second — the key is checked before anything else is asked."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str = ""
        self._base_url: str = DEFAULT_BASE_URL
        self._stations: list[StationSummary] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY].strip()
            self._base_url = user_input.get(CONF_URL, DEFAULT_BASE_URL)
            client = self._build_client()

            try:
                # Verified here rather than at first fetch: a bad key must be rejected while
                # the user is still in the dialog, not hours later as a silent gap.
                await client.async_verify_key()
            except FluvigilAuthError:
                errors["base"] = "invalid_auth"
            except FluvigilRateLimitError:
                errors["base"] = "rate_limited"
            except FluvigilError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_station()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                    vol.Optional(CONF_URL, default=DEFAULT_BASE_URL): str,
                }
            ),
            errors=errors,
        )

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None and CONF_STATION_ID in user_input:
            return await self._create_entry(user_input[CONF_STATION_ID])

        if user_input is not None:
            try:
                self._stations = await self._build_client().async_search_stations(
                    user_input[CONF_SEARCH]
                )
            except FluvigilError:
                errors["base"] = "cannot_connect"
            else:
                if not self._stations:
                    errors["base"] = "no_stations_found"
                else:
                    return await self.async_step_pick()

        return self.async_show_form(
            step_id="station",
            data_schema=vol.Schema({vol.Required(CONF_SEARCH): str}),
            errors=errors,
        )

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._create_entry(user_input[CONF_STATION_ID])

        options = [
            SelectOptionDict(value=station.station_id, label=station.label)
            for station in self._stations
        ]

        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def _create_entry(self, station_id: str) -> ConfigFlowResult:
        # One entry per gauge, so removing one gauge never touches another.
        await self.async_set_unique_id(station_id)
        self._abort_if_unique_id_configured()

        station = next(
            (candidate for candidate in self._stations if candidate.station_id == station_id),
            None,
        )
        title = station.label if station else station_id

        return self.async_create_entry(
            title=title,
            data={
                CONF_API_KEY: self._api_key,
                CONF_URL: self._base_url,
                CONF_STATION_ID: station_id,
                CONF_STATION_NAME: station.name if station else station_id,
            },
        )

    def _build_client(self) -> FluvigilClient:
        return FluvigilClient(
            session=async_get_clientsession(self.hass),
            api_key=self._api_key,
            base_url=self._base_url,
        )
