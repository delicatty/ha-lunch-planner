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

# Which days have a lunch: the work days, the other days, or every day.
SCHEDULE_WORKDAYS = "workdays"
SCHEDULE_WEEKENDS = "weekends"
SCHEDULE_EVERY_DAY = "every_day"
MEAL_SCHEDULES = (SCHEDULE_WORKDAYS, SCHEDULE_WEEKENDS, SCHEDULE_EVERY_DAY)

# Options
CONF_MEAL_SCHEDULE = "meal_schedule"
CONF_WORKDAYS = "workdays"
CONF_MEAL_MODE = "meal_mode"
CONF_SOUP_SHARE = "soup_share"
CONF_AVOID_PREVIOUS_WEEK = "avoid_previous_week"
CONF_WEEK_START = "week_start"
CONF_DRAW_WEEKDAY = "draw_weekday"
CONF_DRAW_TIME = "draw_time"
CONF_NO_SHOPPING_DAYS = "no_shopping_days"
CONF_DAYS_OFF_CALENDARS = "days_off_calendars"
CONF_HOLIDAY_SHOPS_CLOSED = "holiday_shops_closed"
CONF_LUNCH_TIME = "lunch_time"
CONF_LUNCH_DURATION = "lunch_duration"
CONF_SHOW_PANEL = "show_panel"

DEFAULT_OPTIONS = {
    CONF_MEAL_SCHEDULE: SCHEDULE_WORKDAYS,
    CONF_WORKDAYS: ["mon", "tue", "wed", "thu", "fri"],
    CONF_MEAL_MODE: MODE_SOUP_OR_MAIN,
    CONF_SOUP_SHARE: 50,
    CONF_AVOID_PREVIOUS_WEEK: True,
    # The meals of a week are drawn before most of their shopping days. A meal
    # whose shopping day comes before the draw (Monday, bought on Saturday when
    # shops are closed on Sunday) is drawn on its own at midnight.
    CONF_DRAW_WEEKDAY: "sat",
    CONF_DRAW_TIME: "09:00:00",
    CONF_NO_SHOPPING_DAYS: ["sun"],
    # A day with an all-day event in one of these calendars has no lunch.
    CONF_DAYS_OFF_CALENDARS: [],
    # Shops are closed on the days of calendars from the Holiday integration.
    CONF_HOLIDAY_SHOPS_CLOSED: True,
    CONF_LUNCH_TIME: "13:00:00",
    # Minutes; a lunch in the calendar starts at the lunch time and lasts this long.
    CONF_LUNCH_DURATION: 30,
    CONF_SHOW_PANEL: True,
}

# First day of the week by country (CLDR week data); every other country
# starts the week on Monday. Used as the default of the week start option.
_SUNDAY_FIRST = frozenset(
    "AG AS BD BR BS BT BW BZ CA CN CO DM DO ET GT GU HK HN ID IL IN JM JP KE KH "
    "KR LA MH MM MO MT MX MZ NI NP PA PE PH PK PR PT PY SA SG SV TH TT TW UM US "
    "VE VI WS YE ZA ZW".split()
)
_SATURDAY_FIRST = frozenset("AE AF BH DJ DZ EG IQ IR JO KW LY OM QA SD SY".split())
_FRIDAY_FIRST = frozenset({"MV"})


def default_week_start(country: str | None) -> str:
    """First day of the week in ``country`` (ISO code), as an option value."""
    country = (country or "").upper()
    if country in _SUNDAY_FIRST:
        return "sun"
    if country in _SATURDAY_FIRST:
        return "sat"
    if country in _FRIDAY_FIRST:
        return "fri"
    return "mon"


# Option of version 0.5 and older, replaced by the schedule and the work days.
OLD_CONF_MEAL_DAYS = "meal_days"

# Options of version 0.3 that moved to automations (blueprints) in 0.4.
REMOVED_OPTIONS = (
    "shopping_mode",
    "shopping_time",
    "person",
    "arrival_delay",
    "notify_services",
    "shopping_list",
)

# Integration whose calendars hold public holidays (shops closed).
HOLIDAY_PLATFORM = "holiday"
# How far ahead the days-off calendars are read.
DAYS_OFF_AHEAD = 40

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
