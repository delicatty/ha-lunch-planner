"""Constants for Lunch Planner."""

from __future__ import annotations


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

# Options
CONF_MEAL_DAYS = "meal_days"
CONF_MEAL_MODE = "meal_mode"
CONF_SOUP_SHARE = "soup_share"
CONF_AVOID_PREVIOUS_WEEK = "avoid_previous_week"
CONF_DRAW_WEEKDAY = "draw_weekday"
CONF_DRAW_TIME = "draw_time"
CONF_NO_SHOPPING_DAYS = "no_shopping_days"
CONF_LUNCH_TIME = "lunch_time"
CONF_LUNCH_DURATION = "lunch_duration"
CONF_SHOW_PANEL = "show_panel"

DEFAULT_OPTIONS = {
    CONF_MEAL_DAYS: ["mon", "tue", "wed", "thu", "fri"],
    CONF_MEAL_MODE: MODE_SOUP_OR_MAIN,
    CONF_SOUP_SHARE: 50,
    CONF_AVOID_PREVIOUS_WEEK: True,
    # The meals of a week are drawn before most of their shopping days. A meal
    # whose shopping day comes before the draw (Monday, bought on Saturday when
    # shops are closed on Sunday) is drawn on its own at midnight.
    CONF_DRAW_WEEKDAY: "sat",
    CONF_DRAW_TIME: "09:00:00",
    CONF_NO_SHOPPING_DAYS: ["sun"],
    CONF_LUNCH_TIME: "13:00:00",
    # Minutes; a lunch in the calendar starts at the lunch time and lasts this long.
    CONF_LUNCH_DURATION: 30,
    CONF_SHOW_PANEL: True,
}

# Options of version 0.3 that moved to automations (blueprints) in 0.4.
REMOVED_OPTIONS = (
    "shopping_mode",
    "shopping_time",
    "person",
    "arrival_delay",
    "notify_services",
    "shopping_list",
)

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_DATE = "date"

SERVICE_REDRAW = "redraw"
SERVICE_ADD_MEAL = "add_meal"
SERVICE_REMOVE_MEAL = "remove_meal"

EVENT_PLAN_UPDATED = f"{DOMAIN}_plan_updated"
# Why a plan was drawn, in the event data.
REASON_WEEKLY = "weekly"
REASON_REDRAW = "redraw"
REASON_MISSING = "missing"
REASON_FIRST = "first"
