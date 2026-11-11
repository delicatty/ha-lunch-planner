"""Lunch Planner: draws weekday lunches and sends the shopping list."""

from __future__ import annotations

from datetime import date

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DATE,
    DOMAIN,
    PLATFORMS,
    SERVICE_REDRAW,
    SERVICE_SEND_SHOPPING_LIST,
)
from .manager import LunchPlanner
from .panel import async_update_panel

type LunchPlannerConfigEntry = ConfigEntry[LunchPlanner]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_REDRAW_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_DATE): cv.date,
    }
)
_SHOPPING_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})


def _planner_for(hass: HomeAssistant, call: ServiceCall) -> LunchPlanner:
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id:
        entries = [e for e in entries if e.entry_id == entry_id]
    if len(entries) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found" if not entries else "entry_ambiguous",
        )
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services."""

    async def redraw(call: ServiceCall) -> ServiceResponse:
        planner = _planner_for(hass, call)
        day: date | None = call.data.get(ATTR_DATE)
        drawn = planner.async_redraw(day)
        return {"dates": [d.isoformat() for d in drawn]}

    async def send_shopping_list(call: ServiceCall) -> ServiceResponse:
        sent = await _planner_for(hass, call).async_send_shopping()
        return {"sent": sent}

    hass.services.async_register(
        DOMAIN, SERVICE_REDRAW, redraw, _REDRAW_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_SHOPPING_LIST,
        send_shopping_list,
        _SHOPPING_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LunchPlannerConfigEntry) -> bool:
    """Set up a Lunch Planner from a config entry."""
    planner = LunchPlanner(hass, entry)
    await planner.async_load()
    entry.runtime_data = planner
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    planner.async_start()
    entry.async_on_unload(planner.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await async_update_panel(hass, loading=entry.entry_id)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: LunchPlannerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LunchPlannerConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_flush()
        await async_update_panel(hass, unloading=entry.entry_id)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: LunchPlannerConfigEntry) -> None:
    """Delete the stored meal database and plan."""
    await LunchPlanner(hass, entry).async_remove_storage()
