"""Constants for Lunch Planner."""

from __future__ import annotations

from datetime import time

from homeassistant.const import Platform

from .planner import (
    DISH,
    MODE_MAIN_ONLY,
    MODE_SOUP_AND_MAIN,
    MODE_SOUP_ONLY,
    MODE_SOUP_OR_MAIN,
    PROTEIN,
    SALAD,
    SOUP,
    STARCH,
)

DOMAIN = "lunch_planner"
PLATFORMS = [Platform.BUTTON, Platform.CALENDAR, Platform.SENSOR]

STORAGE_VERSION = 1
HISTORY_DAYS = 60

# Database categories, in the order their lists are shown.
CATEGORIES = (SOUP, DISH, PROTEIN, STARCH, SALAD)

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

MEAL_MODES = (MODE_SOUP_OR_MAIN, MODE_SOUP_AND_MAIN, MODE_SOUP_ONLY, MODE_MAIN_ONLY)

SHOPPING_MODE_TIME = "time"
SHOPPING_MODE_PRESENCE = "presence"
SHOPPING_MODES = (SHOPPING_MODE_TIME, SHOPPING_MODE_PRESENCE)

# Options
CONF_MEAL_DAYS = "meal_days"
CONF_MEAL_MODE = "meal_mode"
CONF_SOUP_SHARE = "soup_share"
CONF_AVOID_PREVIOUS_WEEK = "avoid_previous_week"
CONF_DRAW_WEEKDAY = "draw_weekday"
CONF_DRAW_TIME = "draw_time"
CONF_SHOPPING_MODE = "shopping_mode"
CONF_SHOPPING_TIME = "shopping_time"
CONF_PERSON = "person"
CONF_ARRIVAL_DELAY = "arrival_delay"
CONF_NO_SHOPPING_DAYS = "no_shopping_days"
CONF_NOTIFY = "notify_services"
CONF_SHOPPING_LIST = "shopping_list"
CONF_SHOW_PANEL = "show_panel"

DEFAULT_OPTIONS = {
    CONF_MEAL_DAYS: ["mon", "tue", "wed", "thu", "fri"],
    CONF_MEAL_MODE: MODE_SOUP_OR_MAIN,
    CONF_SOUP_SHARE: 50,
    CONF_AVOID_PREVIOUS_WEEK: True,
    # Saturday morning, so the plan exists before shopping for Monday,
    # which happens on Saturday when shops are closed on Sunday.
    CONF_DRAW_WEEKDAY: "sat",
    CONF_DRAW_TIME: "09:00:00",
    CONF_SHOPPING_MODE: SHOPPING_MODE_TIME,
    CONF_SHOPPING_TIME: "17:00:00",
    CONF_ARRIVAL_DELAY: 15,
    CONF_NO_SHOPPING_DAYS: ["sun"],
    CONF_NOTIFY: [],
    CONF_SHOW_PANEL: True,
}

# In presence mode, a shopping list held back while nobody was home is not
# sent after this time; it waits until the next day instead.
LATEST_ARRIVAL_REMINDER = time(22, 0)

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_DATE = "date"

SERVICE_REDRAW = "redraw"
SERVICE_SEND_SHOPPING_LIST = "send_shopping_list"
SERVICE_ADD_MEAL = "add_meal"
SERVICE_REMOVE_MEAL = "remove_meal"

ACTION_REDRAW_PREFIX = "LUNCH_PLANNER_REDRAW_"
EVENT_PLAN_UPDATED = f"{DOMAIN}_plan_updated"
