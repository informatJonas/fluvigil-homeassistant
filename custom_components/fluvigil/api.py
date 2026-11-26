"""Thin client for the Fluvigil public API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp

from .const import REQUEST_TIMEOUT_SECONDS


class FluvigilError(Exception):
    """The service could not be reached or answered unusably."""


class FluvigilAuthError(FluvigilError):
    """The API key is missing, unknown or revoked."""


class FluvigilRateLimitError(FluvigilError):
    """The hourly request budget of the account's tier is exhausted."""


class FluvigilNoValueError(FluvigilError):
    """The service answers, but delivers no value for this gauge.

    Some providers do not licence their values for passing on, and an unknown or blocked
    gauge looks the same.
    """


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
    # The provider's notice, which has to be shown wherever the value is.
    attribution: str | None = None


@dataclass(frozen=True)
class StationSummary:
    """One gauge in the station picker."""

    station_id: str
    name: str
    water: str | None
    # The older `<source>:<id>` of a gauge the service names by a public id.
    legacy_id: str | None = None

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
                legacy_id=entry.get("legacyId"),
            )
            for entry in stations
            if isinstance(entry, dict) and "id" in entry
        ]

    async def async_get_state(self, station_id: str) -> GaugeState:
        payload = await self._get(
            f"/api/v1/stations/{station_id}/state", not_found=FluvigilNoValueError
        )

        return GaugeState(
            station_id=str(payload.get("stationId", station_id)),
            name=str(payload.get("name", station_id)),
            water=payload.get("water"),
            value_centimeters=_as_int(payload.get("valueCentimeters")),
            measured_at=_as_datetime(payload.get("measuredAt")),
            severity=payload.get("severity"),
            headline=payload.get("headline"),
            is_flood=bool(payload.get("isFlood", False)),
            attribution=_as_attribution(payload.get("sourceNotice")),
        )

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
        not_found: type[FluvigilError] = FluvigilError,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {"X-Api-Key": self._api_key, "Accept": "application/json"}

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self._session.get(url, headers=headers, params=params)

                if response.status in (401, 403):
                    raise FluvigilAuthError("Unknown or revoked API key")

                if response.status == 429:
                    raise FluvigilRateLimitError("Hourly request budget exhausted")

                if response.status == 404:
                    raise not_found("Fluvigil answered 404 Not Found")

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
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _as_attribution(notice: Any) -> str | None:
    """The notice of every source involved, one per line; None rather than a made-up text."""
    if not isinstance(notice, dict):
        return None

    parts = notice.get("parts") or [notice]
    texts = [_notice_text(part) for part in parts if isinstance(part, dict)]

    return "\n".join(text for text in texts if text) or None


def _notice_text(part: dict[str, Any]) -> str | None:
    # A `full-only` provider forbids shortening. A short text it may still carry is meant for
    # pages that link the full one, which an attribution does not.
    short = None if part.get("form") == "full-only" else part.get("textShort")
    text = short or part.get("text")

    return text if isinstance(text, str) else None
