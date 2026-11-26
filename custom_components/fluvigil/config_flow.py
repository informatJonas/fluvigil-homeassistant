"""Setup dialog: an API key, then one gauge. Later, a new key for a rejected one."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.data_entry_flow import AbortFlow
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
    FluvigilNoValueError,
    FluvigilRateLimitError,
    StationSummary,
)
from .const import CONF_STATION_ID, CONF_STATION_NAME, DEFAULT_BASE_URL, DOMAIN
from .reauth import async_replace_api_key

CONF_SEARCH = "search"

_ERROR_KEYS: tuple[tuple[type[FluvigilError], str], ...] = (
    (FluvigilAuthError, "invalid_auth"),
    (FluvigilRateLimitError, "rate_limited"),
    (FluvigilNoValueError, "no_value"),
)


def _error_key(error: FluvigilError) -> str:
    return next(
        (key for kind, key in _ERROR_KEYS if isinstance(error, kind)), "cannot_connect"
    )


def _gauge_ids(entry: ConfigEntry) -> set[str]:
    """Every id an entry's gauge is known by without asking the service.

    The stored one may be the older `<source>:<id>`; a loaded entry also holds the id the
    service last answered with.
    """
    ids = {entry.data.get(CONF_STATION_ID)}

    if entry.state is ConfigEntryState.LOADED and entry.runtime_data.data:
        ids.add(entry.runtime_data.data.station_id)

    return ids - {None}


class FluvigilConfigFlow(ConfigFlow, domain=DOMAIN):
    """Key first, gauge second — the key is checked before anything else is asked."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str = ""
        self._base_url: str = DEFAULT_BASE_URL
        self._stations: list[StationSummary] = []
        self._rejected_data: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY].strip()
            self._base_url = user_input.get(CONF_URL, DEFAULT_BASE_URL)

            try:
                # Verified here rather than at first fetch: a bad key must be rejected while
                # the user is still in the dialog, not hours later as a silent gap.
                await self._build_client().async_verify_key()
            except FluvigilError as error:
                errors["base"] = _error_key(error)
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

        if user_input is not None:
            try:
                self._stations = await self._build_client().async_search_stations(
                    user_input[CONF_SEARCH]
                )
            except FluvigilError as error:
                errors["base"] = _error_key(error)
            else:
                if not self._stations:
                    errors["base"] = "no_stations_found"
                else:
                    return await self.async_step_pick()

        return self._show_search(errors)

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

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        # Remembered now: it identifies the entries that share the rejected key.
        self._rejected_data = dict(entry_data)
        self._base_url = entry_data.get(CONF_URL, DEFAULT_BASE_URL)

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY].strip()

            try:
                await self._build_client().async_verify_key()
            except FluvigilError as error:
                errors["base"] = _error_key(error)
            else:
                async_replace_api_key(
                    self.hass, self._rejected_data, self._api_key, self.flow_id
                )

                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    def _show_search(self, errors: dict[str, str]) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="station",
            data_schema=vol.Schema({vol.Required(CONF_SEARCH): str}),
            errors=errors,
        )

    async def _create_entry(self, station_id: str) -> ConfigFlowResult:
        station = next(
            (candidate for candidate in self._stations if candidate.station_id == station_id),
            None,
        )
        self._abort_if_gauge_configured({station_id, station.legacy_id if station else None})

        try:
            # Asked before the entry exists: a gauge without a value would otherwise become
            # a sensor that never shows anything, with no word on why.
            state = await self._build_client().async_get_state(station_id)
        except FluvigilError as error:
            return self._show_search({"base": _error_key(error)})

        self._abort_if_gauge_configured({state.station_id})

        # One entry per gauge, so removing one gauge never touches another.
        await self.async_set_unique_id(station_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=station.label if station else station_id,
            data={
                CONF_API_KEY: self._api_key,
                CONF_URL: self._base_url,
                CONF_STATION_ID: station_id,
                CONF_STATION_NAME: station.name if station else station_id,
            },
        )

    def _abort_if_gauge_configured(self, gauge_ids: set[str | None]) -> None:
        """Catches the same gauge under its other id; existing entries are left as they are."""
        if any(gauge_ids & _gauge_ids(entry) for entry in self._async_current_entries()):
            raise AbortFlow("already_configured")

    def _build_client(self) -> FluvigilClient:
        return FluvigilClient(
            session=async_get_clientsession(self.hass),
            api_key=self._api_key,
            base_url=self._base_url,
        )
