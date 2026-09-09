"""The Fluvigil integration: German water levels from one source."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FluvigilClient
from .const import CONF_STATION_ID, DEFAULT_BASE_URL
from .coordinator import FluvigilCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type FluvigilConfigEntry = ConfigEntry[FluvigilCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: FluvigilConfigEntry) -> bool:
    client = FluvigilClient(
        session=async_get_clientsession(hass),
        api_key=entry.data[CONF_API_KEY],
        base_url=entry.data.get(CONF_URL, DEFAULT_BASE_URL),
    )
    coordinator = FluvigilCoordinator(hass, entry, client, entry.data[CONF_STATION_ID])

    # Fail setup loudly if the first fetch does not work — an integration that loads and
    # then shows nothing is harder to diagnose than one that refuses to load.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: FluvigilConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
