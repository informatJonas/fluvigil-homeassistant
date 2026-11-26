"""The source notice a provider demands wherever its values are shown."""

import pytest
from answers import answer
from homeassistant.core import HomeAssistant
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker
from service import MV_PUBLIC_ID, OLD_ID, gauge_entry, serve_key, set_up


def serve_answer(mocker: AiohttpClientMocker, station_id: str, body: dict) -> None:
    mocker.clear_requests()
    serve_key(mocker)
    mocker.get(f"https://fluvigil.test/api/v1/stations/{station_id}/state", json=body)


@pytest.mark.parametrize(
    ("recorded", "station_id"),
    [("old_app/state_cologne", OLD_ID), ("new_app/state_mv", MV_PUBLIC_ID)],
)
async def test_the_sensor_carries_the_notice_of_its_value_and_only_that(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    recorded: str,
    station_id: str,
) -> None:
    body = answer(recorded)
    serve_answer(aioclient_mock, station_id, body)
    entry = gauge_entry(hass, station_id)

    await set_up(hass, entry)

    sensor = hass.states.async_all("sensor")[0].entity_id
    expected = body["sourceNotice"]["parts"][0]["textShort"]
    assert hass.states.get(sensor).attributes["attribution"] == expected

    # A notice that is gone must not stay on the values that follow.
    serve_answer(aioclient_mock, station_id, {**body, "sourceNotice": None})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert "attribution" not in hass.states.get(sensor).attributes
