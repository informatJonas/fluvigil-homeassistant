"""The setup dialog and the entity it produces, driven inside a real Home Assistant.

These need the framework, which the API-client tests deliberately avoid — but the acceptance
criteria that matter most live exactly here: a bad key must be refused while the user is
still looking at the dialog, and afterwards a sensor must exist with a value, a unit and the
time the gauge was actually read.

HTTP is served by Home Assistant's own request mock rather than a local server, because the
test environment blocks real sockets on purpose.
"""

import shutil
from pathlib import Path

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

_SOURCE = Path(__file__).resolve().parents[2] / "custom_components"

BASE_URL = "https://fluvigil.test"
VALID_KEY = "pm_gueltig"
STATION_ID = "pegelonline:probe"

STATE_PAYLOAD = {
    "stationId": STATION_ID,
    "name": "Probe",
    "water": "Testfluss",
    "valueCentimeters": 412,
    "measuredAt": "2026-09-09T15:00:00.000Z",
    "severity": "normal",
    "headline": "Im Bereich des Mittelwassers",
    "isFlood": False,
}


@pytest.fixture(autouse=True)
def install_integration(hass, enable_custom_integrations):
    """Puts the integration where Home Assistant looks for custom ones.

    Discovery reads the instance's own config directory, which in a test is a throwaway
    folder — copying it there is what makes the loader find it at all.
    """
    shutil.copytree(
        _SOURCE, Path(hass.config.config_dir) / "custom_components", dirs_exist_ok=True
    )
    hass.data.pop("custom_components", None)

    return enable_custom_integrations


def mock_service(mocker: AiohttpClientMocker, *, key_valid: bool = True) -> None:
    mocker.get(
        f"{BASE_URL}/api/v1/me",
        json={"tier": "free", "limits": {}, "organizationId": None} if key_valid else {},
        status=200 if key_valid else 401,
    )
    mocker.get(
        f"{BASE_URL}/api/v1/stations",
        json={"stations": [{"id": STATION_ID, "name": "Probe", "water": "Testfluss"}]},
    )
    mocker.get(f"{BASE_URL}/api/v1/stations/{STATION_ID}/state", json=STATE_PAYLOAD)


async def run_flow(hass: HomeAssistant, api_key: str = VALID_KEY) -> dict:
    """Walks the dialog to the end and returns the final step."""
    flow = hass.config_entries.flow
    result = await flow.async_init("fluvigil", context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"], {"api_key": api_key, "url": BASE_URL}
    )

    if result["type"] is not FlowResultType.FORM or result.get("step_id") != "station":
        return result

    result = await flow.async_configure(result["flow_id"], {"search": "Probe"})

    return await flow.async_configure(result["flow_id"], {"station_id": STATION_ID})


async def test_bad_key_is_refused_in_the_dialog(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_service(aioclient_mock, key_valid=False)

    result = await run_flow(hass, api_key="pm_falsch")

    # Still on the form, with a message — not accepted and then silently useless.
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_unreachable_service_is_reported_as_such(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/me", exc=TimeoutError())

    result = await run_flow(hass)

    assert result["errors"] == {"base": "cannot_connect"}


async def test_rate_limited_key_says_so(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # Distinct from a bad key on purpose: one is fixed with a new key, the other by waiting.
    aioclient_mock.get(f"{BASE_URL}/api/v1/me", status=429, json={})

    result = await run_flow(hass)

    assert result["errors"] == {"base": "rate_limited"}


async def test_setup_produces_a_water_level_sensor(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_service(aioclient_mock)

    result = await run_flow(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Probe (Testfluss)"

    await hass.async_block_till_done()

    state = hass.states.get("sensor.probe_testfluss_water_level")
    assert state is not None, [entity.entity_id for entity in hass.states.async_all()]
    assert state.state == "412"
    assert state.attributes["unit_of_measurement"] == "cm"
    # When the gauge was read, not when we fetched it — only the former says how fresh it is.
    assert state.attributes["measured_at"] == "2026-09-09T15:00:00+00:00"
    assert state.attributes["headline"] == "Im Bereich des Mittelwassers"


async def test_the_same_gauge_cannot_be_added_twice(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_service(aioclient_mock)

    assert (await run_flow(hass))["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    second = await run_flow(hass)

    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_configured"
