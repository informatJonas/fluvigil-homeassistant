"""A stand-in for Fluvigil inside the Home Assistant tests, and the entries talking to it.

HTTP is served by Home Assistant's own request mock, because that test environment blocks
real sockets on purpose.
"""

from typing import Any

from answers import answer
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

BASE_URL = "https://fluvigil.test"
VALID_KEY = "pm_fake_valid_key"

OLD_ID = "pegelonline:a6ee8177-107b-47dd-bcfd-30960ccc6e9c"
PUBLIC_ID = "fp_7K3M9Q2XVD"
MV_OLD_ID = "lhp:MV_04406.0"
MV_PUBLIC_ID = "fp_4N8R2T6WBC"


def serve_key(mocker: AiohttpClientMocker, status: int = 200, base_url: str = BASE_URL) -> None:
    """`/me`: the only route on which the service rejects a key."""
    body = {"tier": "free", "limits": {}, "organizationId": None}

    if status == 401:
        body = answer("new_app/me_rejected")

    mocker.get(f"{base_url}/api/v1/me", json=body, status=status)


def serve_state(
    mocker: AiohttpClientMocker,
    station_id: str,
    recorded: str,
    status: int = 200,
    base_url: str = BASE_URL,
) -> None:
    mocker.get(
        f"{base_url}/api/v1/stations/{station_id}/state", json=answer(recorded), status=status
    )


def serve_search(mocker: AiohttpClientMocker, body: dict[str, Any]) -> None:
    mocker.get(f"{BASE_URL}/api/v1/stations", json=body)


def gauge_entry(
    hass: HomeAssistant,
    station_id: str = OLD_ID,
    api_key: str = VALID_KEY,
    base_url: str = BASE_URL,
) -> MockConfigEntry:
    """An entry as version 0.1 stored it."""
    entry = MockConfigEntry(
        domain="fluvigil",
        title=station_id,
        unique_id=station_id,
        data={
            "api_key": api_key,
            "url": base_url,
            "station_id": station_id,
            "station_name": station_id,
        },
    )
    entry.add_to_hass(hass)

    return entry


async def set_up(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Loads the integration, which sets up every entry added so far."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def run_flow(hass: HomeAssistant, station_id: str, api_key: str = VALID_KEY) -> dict:
    """Walks the setup dialog to the end and returns the final step."""
    flow = hass.config_entries.flow
    result = await flow.async_init("fluvigil", context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"], {"api_key": api_key, "url": BASE_URL}
    )

    if result["type"] is not FlowResultType.FORM or result.get("step_id") != "station":
        return result

    result = await flow.async_configure(result["flow_id"], {"search": "Köln"})

    return await flow.async_configure(result["flow_id"], {"station_id": station_id})
