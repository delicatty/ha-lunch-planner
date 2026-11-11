"""Storage, scheduling and notifications for one Lunch Planner entry."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import random
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_HOME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import planner
from .const import (
    ACTION_REDRAW_PREFIX,
    CATEGORIES,
    CONF_ARRIVAL_DELAY,
    CONF_AVOID_PREVIOUS_WEEK,
    CONF_DRAW_TIME,
    CONF_DRAW_WEEKDAY,
    CONF_MEAL_DAYS,
    CONF_MEAL_MODE,
    CONF_NO_SHOPPING_DAYS,
    CONF_NOTIFY,
    CONF_PERSON,
    CONF_SHOPPING_LIST,
    CONF_SHOPPING_MODE,
    CONF_SHOPPING_TIME,
    CONF_SOUP_SHARE,
    DEFAULT_OPTIONS,
    DOMAIN,
    EVENT_PLAN_UPDATED,
    HISTORY_DAYS,
    LATEST_ARRIVAL_REMINDER,
    SHOPPING_MODE_PRESENCE,
    STORAGE_VERSION,
    WEEKDAYS,
)
from .texts import async_load_texts

_LOGGER = logging.getLogger(__name__)

# A person in one of these states counts as at home: an unknown location must
# not swallow the shopping list.
_HOME_STATES = (STATE_HOME, STATE_UNKNOWN, STATE_UNAVAILABLE)


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
        self.shopping_sent_on: str | None = None
        self.shopping_pending_on: str | None = None
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._arrival_timer: CALLBACK_TYPE | None = None
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
        self.shopping_sent_on = data.get("shopping_sent_on")
        self.shopping_pending_on = data.get("shopping_pending_on")
        if migrated:
            self._schedule_save()

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._data_to_save, 1)

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "plan": self.plan,
            "shopping_sent_on": self.shopping_sent_on,
            "shopping_pending_on": self.shopping_pending_on,
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
        """A day is fixed once its shopping is done or its shopping day passed."""
        today = self.today()
        if day <= today:
            return True
        buy_on = planner.shopping_day(day, self.no_shopping_weekdays)
        return buy_on < today or (buy_on == today and self.shopping_sent_on == today.isoformat())

    @callback
    def _draw(self, days: list[date]) -> list[date]:
        days = [d for d in days if not self.is_locked(d)]
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
        self.hass.bus.async_fire(EVENT_PLAN_UPDATED, {"entry_id": self.entry.entry_id})
        self._changed()
        return days

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
                raise HomeAssistantError(f"{day} is already fixed: its shopping is done")
            return self._draw([day])
        today = self.today()
        days = self.upcoming_days()
        if not days:
            days = planner.rest_of_week_days(today, self.meal_weekdays)
        if not [d for d in days if not self.is_locked(d)]:
            days = planner.next_week_days(today, self.meal_weekdays)
        return self._draw(days)

    @callback
    def async_ensure_plan(self) -> None:
        """Draw the next meal days when nothing is planned ahead (first start)."""
        today = self.today()
        if any(date.fromisoformat(iso) > today for iso in self.plan):
            return
        days = planner.rest_of_week_days(today, self.meal_weekdays)
        if not [d for d in days if not self.is_locked(d)]:
            days = planner.next_week_days(today, self.meal_weekdays)
        self._draw(days)

    async def async_weekly_draw(self) -> None:
        drawn = self._draw(planner.next_week_days(self.today(), self.meal_weekdays))
        if drawn:
            await self.async_send_plan(drawn)

    # -- notifications -----------------------------------------------------

    def describe(self, meal: dict[str, Any], capitalize: bool = True) -> str:
        """The meal in words, in the Home Assistant language."""
        return planner.meal_text(
            meal, self.texts["soup_format"], self.texts["soup_word"], capitalize
        )

    def event_title(self, meal: dict[str, Any]) -> str:
        """Calendar title, e.g. ``Obiad: zupa grzybowa``."""
        return self.texts["event"].format(meal=self.describe(meal, capitalize=False))

    def _day_label(self, day: date) -> str:
        return f"{self.texts[f'weekday_{WEEKDAYS[day.weekday()]}']} {day.strftime('%d.%m')}"

    async def _notify(self, title: str, message: str, data: dict | None = None) -> None:
        for target in self.option(CONF_NOTIFY) or []:
            domain, _, service = target.partition(".")
            if not service:
                domain, service = "notify", target
            payload: dict[str, Any] = {"title": title, "message": message}
            if data and service.startswith("mobile_app_"):
                payload["data"] = data
            try:
                await self.hass.services.async_call(domain, service, payload, blocking=True)
            except HomeAssistantError as err:
                _LOGGER.warning("Could not send notification with %s: %s", target, err)

    async def async_send_plan(self, days: list[date]) -> None:
        lines = []
        for day in sorted(days):
            meal = self.meal_for(day)
            if meal:
                lines.append(f"{self._day_label(day)}: {self.describe(meal)}")
        if not lines:
            return
        await self._notify(
            self.texts["plan_title"],
            "\n".join(lines),
            {
                "tag": f"{DOMAIN}_{self.entry.entry_id}_plan",
                "actions": [
                    {
                        "action": f"{ACTION_REDRAW_PREFIX}{self.entry.entry_id}",
                        "title": self.texts["redraw"],
                    }
                ],
            },
        )

    def meals_to_buy_today(self) -> list[dict[str, Any]]:
        return planner.meals_to_buy_on(self.plan, self.today(), self.no_shopping_weekdays)

    def next_shopping(self) -> tuple[date, list[dict[str, Any]]] | None:
        """The next day with something to buy, and the meals bought for then."""
        today = self.today()
        closed = self.no_shopping_weekdays
        for offset in range(14):
            day = today + timedelta(days=offset)
            if offset == 0 and self.shopping_sent_on == today.isoformat():
                continue
            meals = planner.meals_to_buy_on(self.plan, day, closed)
            if meals:
                return day, meals
        return None

    @callback
    def _draw_missing_for_today(self) -> None:
        """Draw meals that are bought today but not planned yet.

        This covers a weekly draw that has not run yet (e.g. it is set to a
        later day than the first shopping day of the week).
        """
        today = self.today()
        missing = []
        for offset in range(1, 8):
            day = today + timedelta(days=offset)
            if (
                day.weekday() in self.meal_weekdays
                and day.isoformat() not in self.plan
                and planner.shopping_day(day, self.no_shopping_weekdays) == today
            ):
                missing.append(day)
        if missing:
            self._draw(missing)

    async def async_send_shopping(self) -> bool:
        """Send today's shopping list. Returns False when there is nothing to buy."""
        today = self.today()
        self._draw_missing_for_today()
        meals = self.meals_to_buy_today()
        if not meals:
            return False
        items = planner.meal_shopping_items(meals)
        days = ", ".join(self._day_label(date.fromisoformat(m["date"])) for m in meals)
        lines = [
            f"{self._day_label(date.fromisoformat(m['date']))}: {self.describe(m)}"
            for m in meals
        ]
        lines += ["", self.texts["to_buy"], *[f"• {i}" for i in items]]
        await self._notify(
            self.texts["shopping_title"].format(days=days),
            "\n".join(lines),
            {"tag": f"{DOMAIN}_{self.entry.entry_id}_shopping"},
        )
        await self._add_to_shopping_list(items)
        self.shopping_sent_on = today.isoformat()
        self.shopping_pending_on = None
        self._changed()
        return True

    async def _add_to_shopping_list(self, items: list[str]) -> None:
        entity_id = self.option(CONF_SHOPPING_LIST)
        if not entity_id:
            return
        try:
            response = await self.hass.services.async_call(
                "todo",
                "get_items",
                {"entity_id": entity_id, "status": "needs_action"},
                blocking=True,
                return_response=True,
            )
            existing = {
                i["summary"].casefold()
                for i in (response or {}).get(entity_id, {}).get("items", [])
            }
            for item in items:
                if item.casefold() not in existing:
                    await self.hass.services.async_call(
                        "todo", "add_item", {"entity_id": entity_id, "item": item}, blocking=True
                    )
        except HomeAssistantError as err:
            _LOGGER.warning("Could not add to shopping list %s: %s", entity_id, err)

    # -- schedule ----------------------------------------------------------

    def _person_home(self) -> bool:
        person = self.option(CONF_PERSON)
        if not person:
            return True
        state = self.hass.states.get(person)
        return state is None or state.state in _HOME_STATES

    @callback
    def async_start(self) -> None:
        hour, minute, second = _parse_time(self.option(CONF_DRAW_TIME))
        self._unsubs.append(
            async_track_time_change(
                self.hass, self._on_draw_time, hour=hour, minute=minute, second=second
            )
        )
        hour, minute, second = _parse_time(self.option(CONF_SHOPPING_TIME))
        self._unsubs.append(
            async_track_time_change(
                self.hass, self._on_shopping_time, hour=hour, minute=minute, second=second
            )
        )
        person = self.option(CONF_PERSON)
        if self.option(CONF_SHOPPING_MODE) == SHOPPING_MODE_PRESENCE and person:
            self._unsubs.append(
                async_track_state_change_event(self.hass, person, self._on_person_change)
            )
        self._unsubs.append(
            self.hass.bus.async_listen("mobile_app_notification_action", self._on_action)
        )
        # "Today" and "tomorrow" move at midnight.
        self._unsubs.append(
            async_track_time_change(self.hass, self._on_midnight, hour=0, minute=0, second=5)
        )
        self.async_ensure_plan()

    @callback
    def _on_midnight(self, _now: datetime) -> None:
        for update in list(self._listeners):
            update()

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._arrival_timer:
            self._arrival_timer()
            self._arrival_timer = None

    async def _on_draw_time(self, now: datetime) -> None:
        if WEEKDAYS[now.weekday()] == self.option(CONF_DRAW_WEEKDAY):
            await self.async_weekly_draw()

    async def _on_shopping_time(self, now: datetime) -> None:
        if self.shopping_sent_on == self.today().isoformat():
            return
        self._draw_missing_for_today()
        if not self.meals_to_buy_today():
            return
        if self.option(CONF_SHOPPING_MODE) == SHOPPING_MODE_PRESENCE and not self._person_home():
            self.shopping_pending_on = self.today().isoformat()
            self._schedule_save()
            return
        await self.async_send_shopping()

    @callback
    def _on_person_change(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        if self._arrival_timer:
            self._arrival_timer()
            self._arrival_timer = None
        if new_state is None or new_state.state != STATE_HOME:
            return
        delay = int(self.option(CONF_ARRIVAL_DELAY) or 0) * 60
        self._arrival_timer = async_call_later(self.hass, delay, self._on_arrived)

    async def _on_arrived(self, _now: datetime) -> None:
        self._arrival_timer = None
        today = self.today().isoformat()
        if (
            self.shopping_pending_on == today
            and self.shopping_sent_on != today
            and self._person_home()
            and dt_util.now().time() < LATEST_ARRIVAL_REMINDER
        ):
            await self.async_send_shopping()

    async def _on_action(self, event: Event) -> None:
        if event.data.get("action") == f"{ACTION_REDRAW_PREFIX}{self.entry.entry_id}":
            drawn = self.async_redraw()
            if drawn:
                await self.async_send_plan(drawn)
