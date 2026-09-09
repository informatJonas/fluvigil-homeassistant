"""Shared updater for every entity of one Fluvigil config entry."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FluvigilAuthError, FluvigilClient, FluvigilError, FluvigilRateLimitError, GaugeState
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class FluvigilCoordinator(DataUpdateCoordinator[GaugeState]):
    """One updater per config entry, shared by all of its entities.

    Deliberately one and not one per entity: the request cost would otherwise grow with
    every gauge the user adds, and the tier's station allowance would be spent on scheduling
    rather than on gauges.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: FluvigilClient,
        station_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {station_id}",
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self._client = client
        self._station_id = station_id

    async def _async_update_data(self) -> GaugeState:
        try:
            return await self._client.async_get_state(self._station_id)
        except FluvigilAuthError as error:
            # Surfaces as a repair notice asking the user to re-authenticate, rather than
            # as an entity that quietly stops changing.
            raise ConfigEntryAuthFailed(str(error)) from error
        except FluvigilRateLimitError as error:
            raise UpdateFailed(
                "Fluvigil rate limit reached — the account's hourly budget is used up"
            ) from error
        except FluvigilError as error:
            # UpdateFailed marks the entities unavailable. That is the point: a gauge reading
            # that is hours old must not keep being presented as the current one.
            raise UpdateFailed(str(error)) from error
