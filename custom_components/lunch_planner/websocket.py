"""WebSocket commands used by the panel to show and edit the meal database."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import CATEGORIES, DOMAIN
from .manager import LunchPlanner

_MONTH = vol.All(vol.Coerce(int), vol.Range(min=1, max=12))


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_subscribe)
    websocket_api.async_register_command(hass, ws_save)
    websocket_api.async_register_command(hass, ws_delete)


def _planner(hass: HomeAssistant, connection, msg: dict[str, Any]) -> LunchPlanner | None:
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Planner not found")
        return None
    return entry.runtime_data


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/meals/subscribe", vol.Required("entry_id"): str}
)
@callback
def ws_subscribe(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Send the meal database now and after every change."""
    planner = _planner(hass, connection, msg)
    if planner is None:
        return

    @callback
    def send() -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], {"meals": planner.items})
        )

    connection.subscriptions[msg["id"]] = planner.async_add_listener(send)
    connection.send_result(msg["id"])
    send()


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/meals/save",
        vol.Required("entry_id"): str,
        vol.Required("category"): vol.In(CATEGORIES),
        vol.Optional("uid"): str,
        vol.Required("name"): str,
        vol.Optional("ingredients", default=[]): [str],
        vol.Optional("season"): vol.Any(None, vol.ExactSequence([_MONTH, _MONTH])),
        vol.Optional("active", default=True): bool,
    }
)
@callback
def ws_save(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Add a meal, or change the meal with the given uid."""
    planner = _planner(hass, connection, msg)
    if planner is None:
        return
    try:
        uid = planner.save_meal(
            msg["category"],
            msg["name"],
            msg["ingredients"],
            msg.get("season"),
            msg["active"],
            uid=msg.get("uid"),
        )
    except HomeAssistantError as err:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        return
    connection.send_result(msg["id"], {"uid": uid})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/meals/delete",
        vol.Required("entry_id"): str,
        vol.Required("uid"): str,
    }
)
@callback
def ws_delete(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Delete a meal."""
    planner = _planner(hass, connection, msg)
    if planner is None:
        return
    try:
        planner.delete_meal(msg["uid"])
    except HomeAssistantError as err:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        return
    connection.send_result(msg["id"])
