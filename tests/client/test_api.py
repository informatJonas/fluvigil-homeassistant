"""Tests for the Fluvigil API client.

Run against a real aiohttp server rather than a mocking library: the client's whole job is
handling what comes back over HTTP — status codes, malformed bodies, a connection that
fails — and a stub that reimplements those semantics can agree with the client while both
are wrong.
"""

import sys
import types
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web

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
async def test_verify_key_rejects_an_unknown_key():
    # The setup dialog depends on this. Everywhere else on the API an unknown key is ignored
    # and the request proceeds anonymously, which would make a typo look like a working setup.
    routes = [json_route("/api/v1/me", {"statusMessage": "Unknown"}, status=401)]

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
