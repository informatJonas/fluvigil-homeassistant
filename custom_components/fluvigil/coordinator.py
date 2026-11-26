"""Shared updater for every entity of one Fluvigil config entry."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    FluvigilAuthError,
    FluvigilClient,
    FluvigilError,
    FluvigilNoValueError,
    FluvigilRateLimitError,
    GaugeState,
)
from .const import DOMAIN, KEY_CHECK_INTERVAL, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class FluvigilCoordinator(DataUpdateCoordinator[GaugeState | None]):
    """One updater per config entry, shared by all of its entities.

    Deliberately one and not one per entity: the request cost would otherwise grow with
    every gauge the user adds, and the tier's station allowance would be spent on scheduling
    rather than on gauges.

    The data is None while the service delivers nothing for the gauge. That is not a failed
    update: the entry stays loaded and picks the value up when it returns.
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
        self._gauge_label = f"{entry.title} ({station_id})"
        self._key_checked_at: datetime | None = None
        self._key_rejected = False
        self._has_value = True

    async def _async_update_data(self) -> GaugeState | None:
        try:
            await self._async_verify_key_when_due()
            state = await self._client.async_get_state(self._station_id)
        except FluvigilNoValueError:
            state = None
        except FluvigilAuthError as error:
            # The value itself was refused. Polling goes on, so it returns by itself if the
            # service answers again.
            self._ask_for_new_key()
            raise UpdateFailed(str(error)) from error
        except FluvigilRateLimitError as error:
            raise UpdateFailed(
                "Fluvigil rate limit reached — the account's hourly budget is used up"
            ) from error
        except FluvigilError as error:
            # UpdateFailed marks the entities unavailable. That is the point: a gauge reading
            # that is hours old must not keep being presented as the current one.
            raise UpdateFailed(str(error)) from error

        self._log_value_change(state)

        return state

    async def _async_verify_key_when_due(self) -> None:
        now = dt_util.utcnow()

        if self._key_checked_at and now - self._key_checked_at < KEY_CHECK_INTERVAL:
            return

        try:
            await self._client.async_verify_key()
        except FluvigilAuthError:
            self._ask_for_new_key()
        except FluvigilError as error:
            # Only a rejection counts. A check that could not be made is repeated with the
            # next update.
            _LOGGER.debug("Could not check the API key: %s", error)
            return
        else:
            self._key_rejected = False

        self._key_checked_at = now

    def _ask_for_new_key(self) -> None:
        """Open the re-authentication dialog without giving up the readings.

        The values are public and stay true without a key; only the limits of the account's
        tier are lost. An automation that depends on the level must not go blind over that.
        """
        if not self._key_rejected:
            self._key_rejected = True
            _LOGGER.warning(
                "Fluvigil rejects the API key of gauge %s; enter a new one to restore the "
                "limits of your tier",
                self._gauge_label,
            )

        # Does nothing while a dialog for this entry is already open.
        self.config_entry.async_start_reauth(self.hass)

    def _log_value_change(self, state: GaugeState | None) -> None:
        """Say once that a value went missing, and once that it is back."""
        has_value = state is not None and state.value_centimeters is not None

        if has_value == self._has_value:
            return

        self._has_value = has_value

        if has_value:
            _LOGGER.info("Fluvigil provides a value again for gauge %s", self._gauge_label)
            return

        _LOGGER.warning(
            "Fluvigil currently provides no value for gauge %s; its sensor stays "
            "unavailable until a value returns",
            self._gauge_label,
        )
