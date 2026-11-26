"""Tests for the Fluvigil API client.

Run against a real aiohttp server rather than a mocking library: the client's whole job is
handling what comes back over HTTP — status codes, malformed bodies, a connection that
fails — and a stub that reimplements those semantics can agree with the client while both
are wrong.
"""

import asyncio
import sys
import types
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from answers import answer

# Registered here rather than in conftest: only these tests want the client without Home
# Assistant, and aliasing the package globally would shadow the real integration in the
# config-flow tests.
_INTEGRATION_ROOT = Path(__file__).resolve().parents[2] / "custom_components" / "fluvigil"
if "fluvigil" not in sys.modules:
    _package = types.ModuleType("fluvigil")
    _package.__path__ = [str(_INTEGRATION_ROOT)]
    sys.modules["fluvigil"] = _package

from fluvigil.api import (
    FluvigilAuthError,
    FluvigilClient,
    FluvigilError,
    FluvigilNoValueError,
    FluvigilRateLimitError,
)

STATION_ID = "pegelonline:abc"


STATE_PAYLOAD = {
    "stationId": STATION_ID,
    "name": "Köln",
    "water": "Rhein",
    "valueCentimeters": 71,
    "measuredAt": "2026-09-09T14:45:00.000Z",
    "severity": "low",
    "headline": "Sehr niedriger Wasserstand",
    "lhpClass": None,
    "isFlood": False,
}


async def serve(routes: list[web.RouteDef]):
    """Starts a throwaway server and yields a client pointed at it."""
    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]

    return runner, f"http://127.0.0.1:{port}"


async def with_client(routes, callback):
    runner, base_url = await serve(routes)

    try:
        async with aiohttp.ClientSession() as session:
            return await callback(FluvigilClient(session, "pm_testkey", base_url))
    finally:
        await runner.cleanup()


def json_route(path: str, payload: dict, status: int = 200) -> web.RouteDef:
    async def handler(_request: web.Request) -> web.Response:
        return web.json_response(payload, status=status)

    return web.get(path, handler)


@pytest.mark.asyncio
async def test_verify_key_returns_the_tier():
    routes = [json_route("/api/v1/me", {"tier": "pro", "limits": {}})]

    assert await with_client(routes, lambda client: client.async_verify_key()) == "pro"


@pytest.mark.asyncio
@pytest.mark.parametrize("generation", ["old_app", "new_app"])
async def test_verify_key_rejects_an_unknown_key(generation):
    # The setup dialog depends on this. Everywhere else on the API an unknown key is ignored
    # and the request proceeds anonymously, which would make a typo look like a working setup.
    routes = [json_route("/api/v1/me", answer(f"{generation}/me_rejected"), status=401)]

    with pytest.raises(FluvigilAuthError):
        await with_client(routes, lambda client: client.async_verify_key())


@pytest.mark.asyncio
async def test_rate_limit_is_its_own_error():
    # Distinct from an auth failure on purpose: one is fixed with a new key, the other by
    # waiting, and naming the wrong one sends the user to the wrong place.
    routes = [json_route("/api/v1/me", {}, status=429)]

    with pytest.raises(FluvigilRateLimitError):
        await with_client(routes, lambda client: client.async_verify_key())


@pytest.mark.asyncio
async def test_server_error_is_a_plain_failure():
    routes = [json_route("/api/v1/me", {}, status=500)]

    with pytest.raises(FluvigilError):
        await with_client(routes, lambda client: client.async_verify_key())


@pytest.mark.asyncio
async def test_unreachable_service_raises_a_plain_error():
    async with aiohttp.ClientSession() as session:
        # Nothing listening on this port.
        client = FluvigilClient(session, "pm_testkey", "http://127.0.0.1:1")

        with pytest.raises(FluvigilError):
            await client.async_verify_key()


@pytest.mark.asyncio
async def test_a_service_that_does_not_answer_is_a_plain_failure(monkeypatch):
    monkeypatch.setattr("fluvigil.api.REQUEST_TIMEOUT_SECONDS", 0.05)

    async def never_in_time(_request: web.Request) -> web.Response:
        await asyncio.sleep(0.5)

        return web.json_response({"tier": "free"})

    with pytest.raises(FluvigilError, match="did not answer in time"):
        await with_client(
            [web.get("/api/v1/me", never_in_time)], lambda client: client.async_verify_key()
        )


@pytest.mark.asyncio
async def test_get_state_maps_the_payload():
    routes = [json_route(f"/api/v1/stations/{STATION_ID}/state", STATE_PAYLOAD)]

    state = await with_client(routes, lambda client: client.async_get_state(STATION_ID))

    assert state.value_centimeters == 71
    assert state.name == "Köln"
    assert state.water == "Rhein"
    assert state.is_flood is False
    assert state.measured_at is not None
    assert state.measured_at.year == 2026


@pytest.mark.asyncio
async def test_missing_value_stays_none_rather_than_zero():
    # A gauge reporting nothing must not read as a level of zero — zero is a real reading.
    payload = {**STATE_PAYLOAD, "valueCentimeters": None, "measuredAt": None}
    routes = [json_route(f"/api/v1/stations/{STATION_ID}/state", payload)]

    state = await with_client(routes, lambda client: client.async_get_state(STATION_ID))

    assert state.value_centimeters is None
    assert state.measured_at is None


@pytest.mark.asyncio
async def test_unparseable_timestamp_does_not_break_the_reading():
    payload = {**STATE_PAYLOAD, "measuredAt": "gestern"}
    routes = [json_route(f"/api/v1/stations/{STATION_ID}/state", payload)]

    state = await with_client(routes, lambda client: client.async_get_state(STATION_ID))

    assert state.measured_at is None
    assert state.value_centimeters == 71


@pytest.mark.asyncio
async def test_search_skips_malformed_entries():
    payload = {
        "stations": [
            {"id": "pegelonline:1", "name": "Köln", "water": "Rhein"},
            {"name": "kein id-Feld"},
            "gar kein Objekt",
        ]
    }
    routes = [json_route("/api/v1/stations", payload)]

    stations = await with_client(routes, lambda client: client.async_search_stations("Köln"))

    assert len(stations) == 1
    assert stations[0].label == "Köln (Rhein)"


@pytest.mark.asyncio
async def test_unexpected_shape_is_an_error_not_a_crash():
    routes = [json_route("/api/v1/stations", {"unerwartet": True})]

    with pytest.raises(FluvigilError):
        await with_client(routes, lambda client: client.async_search_stations("Köln"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("recorded", "station_id"),
    [
        ("old_app/state_mv_not_found", "lhp:MV_04406.0"),
        ("new_app/state_not_found", "lhp:BY_13321002"),
    ],
)
async def test_a_gauge_the_service_has_no_value_for_is_its_own_error(recorded, station_id):
    # Not an outage: telling the user to check their connection would send them the wrong way.
    path = f"/api/v1/stations/{station_id}/state"
    routes = [json_route(path, answer(recorded), status=404)]

    with pytest.raises(FluvigilNoValueError):
        await with_client(routes, lambda client: client.async_get_state(station_id))


@pytest.mark.asyncio
async def test_an_old_id_is_answered_under_the_public_id():
    recorded = answer("new_app/state_mv")
    routes = [json_route("/api/v1/stations/lhp:MV_04406.0/state", recorded)]

    state = await with_client(routes, lambda client: client.async_get_state("lhp:MV_04406.0"))

    assert state.station_id == recorded["stationId"]
    assert state.value_centimeters == 118


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("generation", "legacy_id"),
    [("old_app", None), ("new_app", "pegelonline:a6ee8177-107b-47dd-bcfd-30960ccc6e9c")],
)
async def test_search_keeps_the_old_id_the_service_names_beside_a_public_one(generation, legacy_id):
    routes = [json_route("/api/v1/stations", answer(f"{generation}/search_cologne"))]

    stations = await with_client(routes, lambda client: client.async_search_stations("Köln"))

    assert stations[0].legacy_id == legacy_id


async def attribution_of(payload: dict) -> str | None:
    routes = [json_route(f"/api/v1/stations/{STATION_ID}/state", payload)]
    state = await with_client(routes, lambda client: client.async_get_state(STATION_ID))

    return state.attribution


@pytest.mark.asyncio
async def test_every_source_of_a_value_is_named():
    recorded = answer("contract/state_two_sources")
    values, station = recorded["sourceNotice"]["parts"]

    assert await attribution_of(recorded) == f"{values['textShort']}\n{station['textShort']}"


@pytest.mark.asyncio
async def test_a_notice_that_must_not_be_shortened_is_passed_on_in_full():
    recorded = answer("contract/state_full_only")
    full_text = recorded["sourceNotice"]["text"]
    # Some providers of this kind do carry a short text, for pages that link their full one.
    recorded["sourceNotice"]["parts"][0]["textShort"] = "Quelle: kurz"

    assert await attribution_of(recorded) == full_text


@pytest.mark.asyncio
async def test_a_notice_without_a_short_text_or_parts_uses_its_text():
    notice = {"form": "short-allowed", "text": "Datenherkunft: Beispiel", "textShort": None}

    assert await attribution_of({**STATE_PAYLOAD, "sourceNotice": notice}) == notice["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("notice", [None, {}, {"parts": []}])
async def test_without_a_notice_nothing_is_made_up(notice):
    assert await attribution_of({**STATE_PAYLOAD, "sourceNotice": notice}) is None
