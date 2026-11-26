"""A key the service no longer accepts: how it is noticed and how one dialog replaces it."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from service import (
    BASE_URL,
    MV_PUBLIC_ID,
    OLD_ID,
    VALID_KEY,
    gauge_entry,
    serve_key,
    serve_state,
    set_up,
)

NEW_KEY = "pm_fake_new_key"
OTHER_KEY = "pm_fake_other_key"
OTHER_URL = "https://other.fluvigil.test"


def pending_reauth(hass: HomeAssistant) -> dict[str, str]:
    """Flow id of every open re-authentication, by the entry it belongs to."""
    return {
        flow["context"]["entry_id"]: flow["flow_id"]
        for flow in hass.config_entries.flow.async_progress_by_handler("fluvigil")
        if flow["context"]["source"] == SOURCE_REAUTH
    }


def serve_everything(mocker: AiohttpClientMocker, key_status: int) -> None:
    mocker.clear_requests()

    for base_url in (BASE_URL, OTHER_URL):
        serve_key(mocker, status=key_status, base_url=base_url)
        serve_state(mocker, OLD_ID, "new_app/state_cologne", base_url=base_url)
        serve_state(mocker, MV_PUBLIC_ID, "new_app/state_mv", base_url=base_url)


async def test_a_key_revoked_during_operation_starts_reauthentication(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    serve_everything(aioclient_mock, key_status=200)
    entry = gauge_entry(hass)
    await set_up(hass, entry)
    assert not pending_reauth(hass)

    # The state route keeps answering: it treats a revoked key as no key at all.
    serve_everything(aioclient_mock, key_status=401)
    freezer.tick(timedelta(hours=1, seconds=1))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert list(pending_reauth(hass)) == [entry.entry_id]


async def test_a_failing_key_check_does_not_take_the_sensor_down(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_key(aioclient_mock, status=503)
    serve_state(aioclient_mock, OLD_ID, "old_app/state_cologne")
    entry = gauge_entry(hass)

    await set_up(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.async_all("sensor")[0].state == "325"
    assert not pending_reauth(hass)


async def test_one_dialog_replaces_the_key_of_every_gauge_that_shared_it(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog,
) -> None:
    serve_everything(aioclient_mock, key_status=401)
    first = gauge_entry(hass, OLD_ID)
    second = gauge_entry(hass, MV_PUBLIC_ID)
    other_key = gauge_entry(hass, "fp_OTHERKEY00", api_key=OTHER_KEY)
    other_server = gauge_entry(hass, "fp_OTHERURL00", base_url=OTHER_URL)
    await set_up(hass, first)
    flows = pending_reauth(hass)
    assert len(flows) == 4

    serve_everything(aioclient_mock, key_status=200)
    result = await hass.config_entries.flow.async_configure(
        flows[first.entry_id], {"api_key": f" {NEW_KEY} "}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"

    for entry in (first, second):
        assert entry.data["api_key"] == NEW_KEY
        assert entry.state is ConfigEntryState.LOADED

    assert other_key.data["api_key"] == OTHER_KEY
    assert other_server.data["api_key"] == VALID_KEY
    assert set(pending_reauth(hass)) == {other_key.entry_id, other_server.entry_id}
    assert not ir.async_get(hass).async_get_issue(
        "homeassistant", f"config_entry_reauth_fluvigil_{second.entry_id}"
    )

    # Existing entities keep their identity, whatever form their id has.
    assert (first.unique_id, second.unique_id) == (OLD_ID, MV_PUBLIC_ID)
    registry = er.async_get(hass)
    assert {
        entity.unique_id
        for entry in (first, second)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    } == {f"{OLD_ID}_water_level", f"{MV_PUBLIC_ID}_water_level"}

    assert VALID_KEY not in caplog.text
    assert NEW_KEY not in caplog.text


async def test_a_rejected_new_key_changes_nothing(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_everything(aioclient_mock, key_status=401)
    first = gauge_entry(hass, OLD_ID)
    second = gauge_entry(hass, MV_PUBLIC_ID)
    await set_up(hass, first)
    flows = pending_reauth(hass)

    result = await hass.config_entries.flow.async_configure(
        flows[first.entry_id], {"api_key": NEW_KEY}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert (first.data["api_key"], second.data["api_key"]) == (VALID_KEY, VALID_KEY)
    assert pending_reauth(hass) == flows
