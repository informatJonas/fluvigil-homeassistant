"""A gauge the service stops delivering a value for, while the integration is running."""

import logging

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from service import MV_OLD_ID, gauge_entry, serve_key, serve_state, set_up


def serve_gauge(mocker: AiohttpClientMocker, recorded: str, status: int = 200) -> None:
    mocker.clear_requests()
    serve_key(mocker)
    serve_state(mocker, MV_OLD_ID, recorded, status=status)


def warnings(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING and record.name.startswith("custom_components.fluvigil")
    ]


async def test_a_gauge_without_a_value_is_unavailable_logged_once_and_recovers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, caplog
) -> None:
    serve_gauge(aioclient_mock, "new_app/state_mv")
    entry = gauge_entry(hass, MV_OLD_ID)
    await set_up(hass, entry)
    sensor = hass.states.async_all("sensor")[0].entity_id
    assert hass.states.get(sensor).state == "118"

    serve_gauge(aioclient_mock, "old_app/state_mv_not_found", status=404)

    for _ in range(3):
        await entry.runtime_data.async_refresh()

    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "unavailable"
    assert len(warnings(caplog)) == 1
    assert "no value" in warnings(caplog)[0]

    serve_gauge(aioclient_mock, "new_app/state_mv")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(sensor).state == "118"
    assert len(warnings(caplog)) == 1


async def test_a_gauge_without_a_value_at_start_waits_for_one(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, caplog
) -> None:
    # Loaded rather than "retrying setup": the entity exists, says it has nothing, and
    # fills in on a later poll without a restart.
    serve_gauge(aioclient_mock, "old_app/state_mv_not_found", status=404)
    entry = gauge_entry(hass, MV_OLD_ID)

    await set_up(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.async_all("sensor")[0].state == "unavailable"
    assert len(warnings(caplog)) == 1
