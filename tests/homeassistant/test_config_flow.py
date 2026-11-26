"""The setup dialog and the entity it produces, driven inside a real Home Assistant.

These need the framework, which the API-client tests deliberately avoid — but the acceptance
criteria that matter most live exactly here: a bad key must be refused while the user is
still looking at the dialog, and afterwards a sensor must exist with a value, a unit and the
time the gauge was actually read.
"""

from answers import answer
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from service import (
    BASE_URL,
    MV_OLD_ID,
    MV_PUBLIC_ID,
    OLD_ID,
    PUBLIC_ID,
    gauge_entry,
    run_flow,
    serve_key,
    serve_search,
    serve_state,
    set_up,
)


def serve_old_app(mocker: AiohttpClientMocker) -> None:
    serve_key(mocker)
    serve_search(mocker, answer("old_app/search_cologne"))
    serve_state(mocker, OLD_ID, "old_app/state_cologne")


async def test_bad_key_is_refused_in_the_dialog(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_key(aioclient_mock, status=401)

    result = await run_flow(hass, OLD_ID, api_key="pm_fake_wrong_key")

    # Still on the form, with a message — not accepted and then silently useless.
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_unreachable_service_is_reported_as_such(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/me", exc=TimeoutError())

    result = await run_flow(hass, OLD_ID)

    assert result["errors"] == {"base": "cannot_connect"}


async def test_rate_limited_key_says_so(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # Distinct from a bad key on purpose: one is fixed with a new key, the other by waiting.
    aioclient_mock.get(f"{BASE_URL}/api/v1/me", status=429, json={})

    result = await run_flow(hass, OLD_ID)

    assert result["errors"] == {"base": "rate_limited"}


async def test_setup_produces_a_water_level_sensor(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_old_app(aioclient_mock)

    result = await run_flow(hass, OLD_ID)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Köln (Rhein)"

    await hass.async_block_till_done()

    state = hass.states.get("sensor.koln_rhein_water_level")
    assert state is not None, [entity.entity_id for entity in hass.states.async_all()]
    assert state.state == "325"
    assert state.attributes["unit_of_measurement"] == "cm"
    # When the gauge was read, not when we fetched it — only the former says how fresh it is.
    assert state.attributes["measured_at"] == "2026-11-26T06:30:00+00:00"
    assert state.attributes["headline"] == "Im Bereich des Mittelwassers"


async def test_the_same_gauge_cannot_be_added_twice(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_old_app(aioclient_mock)

    assert (await run_flow(hass, OLD_ID))["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    second = await run_flow(hass, OLD_ID)

    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_configured"


async def test_a_gauge_without_a_value_is_named_in_the_dialog(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_key(aioclient_mock)
    serve_search(aioclient_mock, {"stations": [{"id": MV_OLD_ID, "name": "Beispielpegel MV"}]})
    serve_state(aioclient_mock, MV_OLD_ID, "old_app/state_mv_not_found", status=404)

    result = await run_flow(hass, MV_OLD_ID)

    # Back at the search, so another gauge can be picked without typing the key again.
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "station"
    assert result["errors"] == {"base": "no_value"}
    assert not hass.config_entries.async_entries("fluvigil")


async def test_the_new_app_offers_the_same_gauge_with_a_value_under_its_public_id(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_key(aioclient_mock)
    serve_search(aioclient_mock, answer("new_app/search_mv"))
    serve_state(aioclient_mock, MV_PUBLIC_ID, "new_app/state_mv")

    result = await run_flow(hass, MV_PUBLIC_ID)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == MV_PUBLIC_ID


async def test_a_gauge_stored_under_its_old_id_is_not_added_again_under_the_public_one(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # Not loaded, so only the old id the search names beside the public one can tell.
    existing = gauge_entry(hass, OLD_ID)
    serve_key(aioclient_mock)
    serve_search(aioclient_mock, answer("new_app/search_cologne"))
    serve_state(aioclient_mock, PUBLIC_ID, "new_app/state_cologne")

    result = await run_flow(hass, PUBLIC_ID)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert existing.unique_id == OLD_ID


async def test_a_loaded_old_entry_is_recognised_by_the_public_id_its_state_names(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # Once the service stops naming old ids in the search, the answer the loaded entry
    # already holds is what connects the two.
    serve_key(aioclient_mock)
    serve_state(aioclient_mock, OLD_ID, "new_app/state_cologne")
    serve_state(aioclient_mock, PUBLIC_ID, "new_app/state_cologne")
    serve_search(aioclient_mock, {"stations": [{"id": PUBLIC_ID, "name": "Köln"}]})
    await set_up(hass, gauge_entry(hass, OLD_ID))

    result = await run_flow(hass, PUBLIC_ID)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_an_old_id_is_recognised_as_a_gauge_stored_under_its_public_id(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # The reverse direction: only the state of the picked id names the public one.
    gauge_entry(hass, PUBLIC_ID)
    serve_key(aioclient_mock)
    serve_search(aioclient_mock, {"stations": [{"id": OLD_ID, "name": "Köln"}]})
    serve_state(aioclient_mock, OLD_ID, "new_app/state_cologne")

    result = await run_flow(hass, OLD_ID)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
