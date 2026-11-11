"""The "Lunch planner" sidebar panel.

One panel serves every planner. It shows today's and tomorrow's lunch, the
buttons, the plan calendar and the five meal-database lists, using Home
Assistant's own cards. The lists are hidden from the To-do panel by default,
so this panel is where the database is edited.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .const import CONF_SHOW_PANEL, DEFAULT_OPTIONS, DOMAIN
from .texts import async_load_texts

PANEL_URL_PATH = "lunch-planner"
PANEL_COMPONENT = "lunch-planner-panel"
STATIC_URL = "/lunch_planner_static"
_STATIC_REGISTERED = f"{DOMAIN}_static_registered"
_FRONTEND_DIR = Path(__file__).parent / "frontend"

# Entities shown in the panel, by the key in their unique ID.
_KEYS = ("today", "tomorrow", "next_shopping", "to_buy", "redraw", "plan")


def _planner_config(hass: HomeAssistant, entry_id: str, title: str) -> dict[str, Any]:
    registry = er.async_get(hass)
    by_key = {}
    for entity in er.async_entries_for_config_entry(registry, entry_id):
        key = entity.unique_id.removeprefix(f"{entry_id}_")
        if key in _KEYS:
            by_key[key] = entity.entity_id
    return {"entry_id": entry_id, "title": title, "entities": by_key}


async def async_update_panel(
    hass: HomeAssistant, *, loading: str | None = None, unloading: str | None = None
) -> None:
    """Show the panel for the loaded planners that want it, or remove it.

    ``loading`` is the entry being set up right now (its state is not LOADED
    yet), ``unloading`` the one being unloaded (still LOADED).
    """
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if (e.state is ConfigEntryState.LOADED or e.entry_id == loading)
        and e.entry_id != unloading
        and e.options.get(CONF_SHOW_PANEL, DEFAULT_OPTIONS[CONF_SHOW_PANEL])
    ]
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    if not entries:
        return

    if not hass.data.get(_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(_FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[_STATIC_REGISTERED] = True

    if len(entries) == 1:
        title = entries[0].title
    else:
        title = (await async_load_texts(hass)).get("default_name", "Lunch planner")
    # The version in the URL makes browsers load the new script after an update.
    version = (await async_get_integration(hass, DOMAIN)).version
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title=title,
        sidebar_icon="mdi:silverware-fork-knife",
        module_url=f"{STATIC_URL}/panel.js?v={version}",
        config={
            "title": title,
            "planners": [_planner_config(hass, e.entry_id, e.title) for e in entries],
        },
        require_admin=False,
    )
