"""Storage and scheduling for one Lunch Planner entry."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import random
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import planner
from .const import (
    CATEGORIES,
    CONF_AVOID_PREVIOUS_WEEK,
    CONF_DRAW_TIME,
    CONF_DRAW_WEEKDAY,
    CONF_MEAL_DAYS,
    CONF_MEAL_MODE,
    CONF_NO_SHOPPING_DAYS,
    CONF_SOUP_SHARE,
    DEFAULT_OPTIONS,
    DOMAIN,
    EVENT_PLAN_UPDATED,
    HISTORY_DAYS,
    REASON_FIRST,
    REASON_MISSING,
    REASON_REDRAW,
    REASON_WEEKLY,
    STORAGE_VERSION,
    WEEKDAYS,
)
from .texts import async_load_texts

_LOGGER = logging.getLogger(__name__)


def _weekday_numbers(names: list[str]) -> list[int]:
    return [WEEKDAYS.index(n) for n in names if n in WEEKDAYS]


def _clean_meal(meal: dict[str, Any]) -> dict[str, Any]:
    """Normalise a meal: trimmed name, unique non-empty ingredients, valid season."""
    name = str(meal.get("name", "")).strip()
    if not name:
        raise HomeAssistantError("A meal needs a name")
    ingredients: list[str] = []
    for raw in meal.get("ingredients") or []:
        item = str(raw).strip()
        if item and item.casefold() not in (i.casefold() for i in ingredients):
            ingredients.append(item)
    season = meal.get("season")
    if season:
        start, end = (int(m) for m in season)
        if not (1 <= start <= 12 and 1 <= end <= 12):
            raise HomeAssistantError("Season months must be 1-12")
        season = [start, end]
    else:
        season = None
    return {
        "uid": meal["uid"],
        "name": name,
        "ingredients": ingredients,
        "season": season,
        "active": bool(meal.get("active", True)),
    }


def _migrate_meal(meal: dict[str, Any]) -> dict[str, Any]:
    """Convert a stored to-do item (version 0.2) into a meal."""
    if "summary" not in meal:
        return meal
    item = planner.parse_item(meal["uid"], meal["summary"], meal.get("description"))
    return {
        "uid": meal["uid"],
        "name": item.name,
        "ingredients": list(item.ingredients),
        "season": list(item.season) if item.season else None,
        "active": not meal.get("done", False),
    }


def _parse_time(value: str) -> tuple[int, int, int]:
    parts = [int(p) for p in str(value).split(":")] + [0, 0]
    return parts[0], parts[1], parts[2]


class LunchPlanner:
    """Holds the meal database and the plan, and runs the schedule."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.items: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
        self.plan: dict[str, dict[str, Any]] = {}
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._rng = random.Random()
        self._texts: dict[str, str] = {}

    # -- options ---------------------------------------------------------

    def option(self, key: str) -> Any:
        return self.entry.options.get(key, DEFAULT_OPTIONS.get(key))

    @property
    def meal_weekdays(self) -> list[int]:
        return _weekday_numbers(self.option(CONF_MEAL_DAYS))

    @property
    def no_shopping_weekdays(self) -> list[int]:
        return _weekday_numbers(self.option(CONF_NO_SHOPPING_DAYS))

    @property
    def planner_options(self) -> planner.PlannerOptions:
        return planner.PlannerOptions(
            meal_mode=self.option(CONF_MEAL_MODE),
            soup_share=int(self.option(CONF_SOUP_SHARE)),
            avoid_previous_week=bool(self.option(CONF_AVOID_PREVIOUS_WEEK)),
        )

    @property
    def texts(self) -> dict:
        return self._texts

    # -- storage ---------------------------------------------------------

    async def async_load(self) -> None:
        self._texts = await async_load_texts(self.hass)
        data = await self._store.async_load() or {}
        stored_items = data.get("items", {})
        self.items = {
            c: [_migrate_meal(m) for m in stored_items.get(c, [])] for c in CATEGORIES
        }
        migrated = any("summary" in m for c in stored_items.values() for m in c)
        self.plan = dict(data.get("plan", {}))
        if migrated:
            self._schedule_save()

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._data_to_save, 1)

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "plan": self.plan,
        }

    async def async_flush(self) -> None:
        """Write pending changes now (a reload must not lose recent edits)."""
        await self._store.async_save(self._data_to_save())

    async def async_remove_storage(self) -> None:
        await self._store.async_remove()

    # -- listeners -------------------------------------------------------

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _changed(self) -> None:
        self._schedule_save()
        for update in list(self._listeners):
            update()

    # -- meal database -----------------------------------------------------

    def _find(self, uid: str) -> tuple[str, dict[str, Any]]:
        for category, meals in self.items.items():
            for meal in meals:
                if meal["uid"] == uid:
                    return category, meal
        raise HomeAssistantError(f"Meal {uid} not found")

    @callback
    def save_meal(
        self,
        category: str,
        name: str,
        ingredients: list[str],
        season: tuple[int, int] | list[int] | None,
        active: bool,
        uid: str | None = None,
    ) -> str:
        """Add a meal, or update the meal ``uid`` (moving it to ``category``)."""
        meal = _clean_meal(
            {"uid": uid or uuid.uuid4().hex, "name": name, "ingredients": ingredients,
             "season": season, "active": active}
        )
        if uid is not None:
            old_category, old = self._find(uid)
            if old_category == category:
                old.update(meal)
                self._changed()
                return uid
            self.items[old_category].remove(old)
        self.items[category].append(meal)
        self._changed()
        return meal["uid"]

    @callback
    def delete_meal(self, uid: str) -> None:
        category, meal = self._find(uid)
        self.items[category].remove(meal)
        self._changed()

    def find_by_name(self, category: str, name: str) -> dict[str, Any] | None:
        key = name.strip().casefold()
        return next((m for m in self.items[category] if m["name"].casefold() == key), None)

    def catalog(self) -> dict[str, list[planner.Item]]:
        """The database as planner items; meals switched off are excluded."""
        return {
            category: [
                planner.Item(
                    uid=m["uid"],
                    name=m["name"],
                    ingredients=tuple(m["ingredients"]),
                    season=tuple(m["season"]) if m["season"] else None,
                )
                for m in meals
                if m["active"]
            ]
            for category, meals in self.items.items()
        }

    # -- plan ------------------------------------------------------------

    def today(self) -> date:
        return dt_util.now().date()

    def meal_for(self, day: date) -> dict[str, Any] | None:
        return self.plan.get(day.isoformat())

    def is_locked(self, day: date) -> bool:
        """A day is fixed from the start of the day its shopping is done on.

        From then on the shopping list for it may already be out, so drawing
        again must not change it.
        """
        today = self.today()
        return day <= today or planner.shopping_day(day, self.no_shopping_weekdays) <= today

    @callback
    def _draw(self, days: list[date], reason: str) -> list[date]:
        # A locked day keeps its meal; a future day with no meal can always get one.
        today = self.today()
        days = [
            d
            for d in days
            if d > today and (not self.is_locked(d) or d.isoformat() not in self.plan)
        ]
        if not days:
            return []
        drawn = planner.plan_days(
            days, self.catalog(), self.planner_options, history=self.plan, rng=self._rng
        )
        for day in days:
            iso = day.isoformat()
            if iso in drawn:
                self.plan[iso] = drawn[iso]
            else:
                self.plan.pop(iso, None)
        oldest = (self.today() - timedelta(days=HISTORY_DAYS)).isoformat()
        self.plan = {iso: meal for iso, meal in sorted(self.plan.items()) if iso >= oldest}
        self.hass.bus.async_fire(EVENT_PLAN_UPDATED, self._plan_event(days, reason))
        self._changed()
        return days

    def _plan_event(self, drawn: list[date], reason: str) -> dict[str, Any]:
        """Event data, ready to be put into a notification by an automation.

        ``meals`` and ``summary`` cover every planned day from tomorrow to the
        end of the last drawn day's week, so a weekly draw also lists a Monday
        that was drawn earlier because its shopping day had come.
        """
        last = max(drawn)
        week_end = last + timedelta(days=6 - last.weekday())
        today = self.today()
        meals = [
            {
                "date": iso,
                "label": self.day_label(date.fromisoformat(iso)),
                "meal": self.describe(meal),
                "shopping_items": planner.meal_shopping_items([meal]),
            }
            for iso, meal in sorted(self.plan.items())
            if today < date.fromisoformat(iso) <= week_end
        ]
        return {
            "entry_id": self.entry.entry_id,
            "reason": reason,
            "drawn": [d.isoformat() for d in sorted(drawn)],
            "meals": meals,
            "summary": "\n".join(f"{m['label']}: {m['meal']}" for m in meals),
        }

    def upcoming_days(self) -> list[date]:
        """Planned days after today that can still change."""
        today = self.today()
        return [
            day
            for day in (date.fromisoformat(iso) for iso in self.plan)
            if day > today and not self.is_locked(day)
        ]

    @callback
    def async_redraw(self, day: date | None = None) -> list[date]:
        """Draw one day again, or all upcoming days that can still change."""
        if day is not None:
            if day.weekday() not in self.meal_weekdays:
                raise HomeAssistantError(f"{day} is not a meal day")
            if self.is_locked(day):
                raise HomeAssistantError(f"{day} is already fixed: its shopping day has come")
            return self._draw([day], REASON_REDRAW)
        today = self.today()
        days = self.upcoming_days()
        if not days:
            days = planner.rest_of_week_days(today, self.meal_weekdays)
        if not [d for d in days if not self.is_locked(d)]:
            days = planner.next_week_days(today, self.meal_weekdays)
        return self._draw(days, REASON_REDRAW)

    @callback
    def async_ensure_plan(self) -> None:
        """Draw the next meal days when nothing is planned ahead (first start)."""
        today = self.today()
        if any(date.fromisoformat(iso) > today for iso in self.plan):
            return
        days = planner.rest_of_week_days(today, self.meal_weekdays)
        if not [d for d in days if not self.is_locked(d)]:
            days = planner.next_week_days(today, self.meal_weekdays)
        self._draw(days, REASON_FIRST)

    @callback
    def async_weekly_draw(self) -> list[date]:
        return self._draw(planner.next_week_days(self.today(), self.meal_weekdays), REASON_WEEKLY)

    @callback
    def _draw_missing(self) -> None:
        """Draw meals whose shopping day has come but which are not planned yet.

        E.g. when the weekly draw is set later than the first shopping day of
        the week. Runs at start-up and at midnight.
        """
        today = self.today()
        missing = []
        for offset in range(1, 9):
            day = today + timedelta(days=offset)
            if (
                day.weekday() in self.meal_weekdays
                and day.isoformat() not in self.plan
                and planner.shopping_day(day, self.no_shopping_weekdays) <= today
            ):
                missing.append(day)
        if missing:
            self._draw(missing, REASON_MISSING)

    # -- texts -------------------------------------------------------------

    def describe(self, meal: dict[str, Any], capitalize: bool = True) -> str:
        """The meal in words, in the Home Assistant language."""
        return planner.meal_text(
            meal, self.texts["soup_format"], self.texts["soup_word"], capitalize
        )

    def event_title(self, meal: dict[str, Any]) -> str:
        """Calendar title, e.g. ``Obiad: zupa grzybowa``."""
        return self.texts["event"].format(meal=self.describe(meal, capitalize=False))

    def day_label(self, day: date) -> str:
        """Short day name and date, e.g. ``pon 16.11``."""
        return f"{self.texts[f'weekday_{WEEKDAYS[day.weekday()]}']} {day.strftime('%d.%m')}"

    # -- shopping ------------------------------------------------------------

    def next_shopping(self) -> tuple[date, list[dict[str, Any]]] | None:
        """The next day (today or later) with something to buy, and its meals."""
        today = self.today()
        for offset in range(14):
            day = today + timedelta(days=offset)
            meals = planner.meals_to_buy_on(self.plan, day, self.no_shopping_weekdays)
            if meals:
                return day, meals
        return None

    # -- schedule ----------------------------------------------------------

    @callback
    def async_start(self) -> None:
        hour, minute, second = _parse_time(self.option(CONF_DRAW_TIME))
        self._unsubs.append(
            async_track_time_change(
                self.hass, self._on_draw_time, hour=hour, minute=minute, second=second
            )
        )
        # "Today", "tomorrow" and the next shopping day move at midnight.
        self._unsubs.append(
            async_track_time_change(self.hass, self._on_midnight, hour=0, minute=0, second=5)
        )
        self.async_ensure_plan()
        self._draw_missing()

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def _on_draw_time(self, now: datetime) -> None:
        if WEEKDAYS[now.weekday()] == self.option(CONF_DRAW_WEEKDAY):
            self.async_weekly_draw()

    @callback
    def _on_midnight(self, _now: datetime) -> None:
        self._draw_missing()
        for update in list(self._listeners):
            update()
