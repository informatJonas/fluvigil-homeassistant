"""Thin client for the Fluvigil public API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp
import async_timeout

from .const import REQUEST_TIMEOUT_SECONDS


class FluvigilError(Exception):
    """The service could not be reached or answered unusably."""


class FluvigilAuthError(FluvigilError):
    """The API key is missing, unknown or revoked."""


class FluvigilRateLimitError(FluvigilError):
    """The hourly request budget of the account's tier is exhausted."""


@dataclass(frozen=True)
class GaugeState:
    """Current state of one gauge, as the /state endpoint reports it."""

    station_id: str
    name: str
    water: str | None
    value_centimeters: int | None
    measured_at: datetime | None
    severity: str | None
    headline: str | None
    is_flood: bool


@dataclass(frozen=True)
class StationSummary:
    """One gauge in the station picker."""

    station_id: str
    name: str
    water: str | None

    @property
    def label(self) -> str:
        return f"{self.name} ({self.water})" if self.water else self.name


class FluvigilClient:
    """Talks to Fluvigil. One instance per config entry."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, base_url: str) -> None:
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def async_verify_key(self) -> str:
        """Confirm the key and return its tier.

        The rest of the API ignores an unrecognised key and answers as anonymous, so a typo
        would look like a working setup on free-tier limits. This endpoint rejects it, which
        is what lets the config flow complain while the user is still looking at the dialog.
        """
        payload = await self._get("/api/v1/me")
        tier = payload.get("tier")

        if not isinstance(tier, str):
            raise FluvigilError("Unexpected response while verifying the API key")

        return tier

    async def async_search_stations(self, query: str) -> list[StationSummary]:
        payload = await self._get("/api/v1/stations", params={"q": query})
        stations = payload.get("stations")

        if not isinstance(stations, list):
            raise FluvigilError("Unexpected response while searching stations")

        return [
            StationSummary(
                station_id=str(entry["id"]),
                name=str(entry.get("name", entry["id"])),
                water=entry.get("water"),
            )
            for entry in stations
            if isinstance(entry, dict) and "id" in entry
        ]

    async def async_get_state(self, station_id: str) -> GaugeState:
        payload = await self._get(f"/api/v1/stations/{station_id}/state")

        return GaugeState(
            station_id=str(payload.get("stationId", station_id)),
            name=str(payload.get("name", station_id)),
            water=payload.get("water"),
            value_centimeters=_as_int(payload.get("valueCentimeters")),
            measured_at=_as_datetime(payload.get("measuredAt")),
            severity=payload.get("severity"),
            headline=payload.get("headline"),
            is_flood=bool(payload.get("isFlood", False)),
        )

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {"X-Api-Key": self._api_key, "Accept": "application/json"}

        try:
            async with async_timeout.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self._session.get(url, headers=headers, params=params)

                if response.status in (401, 403):
                    raise FluvigilAuthError("Unknown or revoked API key")

                if response.status == 429:
                    raise FluvigilRateLimitError("Hourly request budget exhausted")

                response.raise_for_status()
                payload = await response.json()
        except FluvigilError:
            raise
        except aiohttp.ClientError as error:
            raise FluvigilError(f"Could not reach Fluvigil: {error}") from error
        except TimeoutError as error:
            raise FluvigilError("Fluvigil did not answer in time") from error

        if not isinstance(payload, dict):
            raise FluvigilError("Unexpected response shape")

        return payload


def _as_int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _as_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
