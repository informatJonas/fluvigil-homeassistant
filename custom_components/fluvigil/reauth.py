"""Replacing a rejected API key for every gauge that used it."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DEFAULT_BASE_URL, DOMAIN


@callback
def async_replace_api_key(
    hass: HomeAssistant, old_data: dict[str, str], new_key: str, own_flow_id: str
) -> None:
    """Give every entry of the same key and server the new key, and close their dialogs.

    There is one entry per gauge and Home Assistant opens one re-authentication per entry.
    Revoking a key therefore raises as many as there are gauges; answering one answers all.
    Unique ids stay as they are.
    """
    replaced: set[str] = set()

    for entry in hass.config_entries.async_entries(DOMAIN):
        if not _shares_account(entry, old_data):
            continue

        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_API_KEY: new_key}
        )
        hass.config_entries.async_schedule_reload(entry.entry_id)
        replaced.add(entry.entry_id)

    flows = hass.config_entries.flow

    for flow in flows.async_progress_by_handler(DOMAIN, match_context={"source": SOURCE_REAUTH}):
        if flow["flow_id"] != own_flow_id and flow["context"].get("entry_id") in replaced:
            flows.async_abort(flow["flow_id"])

    # Before 2025 an aborted flow left its repair notice behind. Removing a notice that is
    # already gone does nothing.
    for entry_id in replaced:
        ir.async_delete_issue(
            hass, HOMEASSISTANT_DOMAIN, f"config_entry_reauth_{DOMAIN}_{entry_id}"
        )


def _shares_account(entry: ConfigEntry, old_data: dict[str, str]) -> bool:
    """The same key against the same server. The same key elsewhere is another account."""
    return entry.data.get(CONF_API_KEY) == old_data[CONF_API_KEY] and _server(
        entry.data
    ) == _server(old_data)


def _server(data: dict[str, str]) -> str:
    return data.get(CONF_URL, DEFAULT_BASE_URL).rstrip("/")
