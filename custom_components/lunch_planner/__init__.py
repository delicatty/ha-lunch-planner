"""Lunch Planner: draws weekday lunches and sends the shopping list."""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.typing import ConfigType

from . import websocket
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DATE,
    CATEGORIES,
    DOMAIN,
    PLATFORMS,
    SERVICE_ADD_MEAL,
    SERVICE_REDRAW,
    REMOVED_OPTIONS,
    SERVICE_REMOVE_MEAL,
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


def _text_list(value: Any) -> list[str]:
    """Ingredients as a list, or as text with one per line or comma-separated."""
    if isinstance(value, str):
        return [p.strip() for line in value.splitlines() for p in line.split(",") if p.strip()]
    return [str(v) for v in cv.ensure_list(value)]


_MONTH = vol.All(vol.Coerce(int), vol.Range(min=1, max=12))
_ADD_MEAL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required("category"): vol.In(CATEGORIES),
        vol.Required("name"): cv.string,
        vol.Optional("ingredients", default=[]): _text_list,
        vol.Optional("season_from"): _MONTH,
        vol.Optional("season_to"): _MONTH,
        vol.Optional("active", default=True): cv.boolean,
    }
)
_REMOVE_MEAL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required("category"): vol.In(CATEGORIES),
        vol.Required("name"): cv.string,
    }
)


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

    async def add_meal(call: ServiceCall) -> None:
        planner = _planner_for(hass, call)
        start, end = call.data.get("season_from"), call.data.get("season_to")
        if (start is None) != (end is None):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="season_incomplete"
            )
        existing = planner.find_by_name(call.data["category"], call.data["name"])
        planner.save_meal(
            call.data["category"],
            call.data["name"],
            call.data["ingredients"],
            (start, end) if start is not None else None,
            call.data["active"],
            uid=existing["uid"] if existing else None,
        )

    async def remove_meal(call: ServiceCall) -> None:
        planner = _planner_for(hass, call)
        meal = planner.find_by_name(call.data["category"], call.data["name"])
        if meal is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="meal_not_found",
                translation_placeholders={"name": call.data["name"]},
            )
        planner.delete_meal(meal["uid"])

    hass.services.async_register(DOMAIN, SERVICE_ADD_MEAL, add_meal, _ADD_MEAL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_MEAL, remove_meal, _REMOVE_MEAL_SCHEMA)
    websocket.async_register(hass)
    hass.services.async_register(
        DOMAIN, SERVICE_REDRAW, redraw, _REDRAW_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """1.1 -> 1.2: notifications moved to automations, drop their options."""
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        options = {k: v for k, v in entry.options.items() if k not in REMOVED_OPTIONS}
        hass.config_entries.async_update_entry(entry, options=options, minor_version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LunchPlannerConfigEntry) -> bool:
    """Set up a Lunch Planner from a config entry."""
    planner = LunchPlanner(hass, entry)
    await planner.async_load()
    entry.runtime_data = planner
    _remove_old_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    planner.async_start()
    entry.async_on_unload(planner.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await async_update_panel(hass, loading=entry.entry_id)
    return True


def _remove_old_entities(hass: HomeAssistant, entry: LunchPlannerConfigEntry) -> None:
    """Remove entities of earlier versions.

    0.2 kept the meal database in to-do lists (the panel replaced them);
    0.3 had a "send shopping list now" button (automations send it now).
    """
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == "todo" or entity.unique_id == f"{entry.entry_id}_send_shopping":
            registry.async_remove(entity.entity_id)


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
