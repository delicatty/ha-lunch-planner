"""Storage and scheduling for one Lunch Planner entry."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import logging
import random
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import planner
from .const import (
    CATEGORIES,
    CONF_AVOID_PREVIOUS_WEEK,
    CONF_DAYS_OFF_CALENDARS,
    CONF_DRAW_TIME,
    CONF_DRAW_WEEKDAY,
    CONF_HOLIDAY_SHOPS_CLOSED,
    CONF_LUNCH_DURATION,
    CONF_LUNCH_TIME,
    CONF_MEAL_MODE,
    CONF_MEAL_SCHEDULE,
    CONF_NO_SHOPPING_DAYS,
    CONF_SOUP_DAYS,
    CONF_SOUP_WEEKDAYS,
    CONF_WEEK_START,
    CONF_WORKDAYS,
    DAYS_OFF_AHEAD,
    DEFAULT_OPTIONS,
    DOMAIN,
    EVENT_PLAN_UPDATED,
    HISTORY_DAYS,
    HOLIDAY_PLATFORM,
    LOCK_TIME,
    REASON_FIRST,
    REASON_MISSING,
    REASON_REDRAW,
    REASON_SWAP,
    REASON_WEEKLY,
    SCHEDULE_EVERY_DAY,
    SCHEDULE_WEEKENDS,
    STORAGE_VERSION,
    WEEKDAYS,
    default_week_start,
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


def _all_day_dates(events: list[dict[str, Any]]) -> set[date]:
    """Dates covered by the all-day events among ``events`` (end is exclusive)."""
    days: set[date] = set()
    for event in events:
        start, end = event.get("start"), event.get("end")
        if isinstance(start, str) and len(start) == 10:
            start = date.fromisoformat(start)
        if isinstance(end, str) and len(end) == 10:
            end = date.fromisoformat(end)
        if type(start) is not date or type(end) is not date:
            continue  # an event with a time of day is not a day off
        day = start
        while day < max(end, start + timedelta(days=1)):
            days.add(day)
            day += timedelta(days=1)
    return days


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
        # Days with an all-day event, per days-off calendar.
        self._calendar_days: dict[str, set[date]] = {}

    # -- options ---------------------------------------------------------

    def option(self, key: str) -> Any:
        if key == CONF_WEEK_START and key not in self.entry.options:
            return default_week_start(self.hass.config.country)
        return self.entry.options.get(key, DEFAULT_OPTIONS.get(key))

    @property
    def week_start(self) -> int:
        return WEEKDAYS.index(self.option(CONF_WEEK_START))

    @property
    def meal_weekdays(self) -> list[int]:
        workdays = _weekday_numbers(self.option(CONF_WORKDAYS))
        schedule = self.option(CONF_MEAL_SCHEDULE)
        if schedule == SCHEDULE_EVERY_DAY:
            return list(range(7))
        if schedule == SCHEDULE_WEEKENDS:
            return [d for d in range(7) if d not in workdays]
        return workdays

    @property
    def days_off(self) -> set[date]:
        """Days with an all-day event in one of the days-off calendars."""
        return set().union(*self._calendar_days.values())

    @property
    def shops_closed(self) -> set[date]:
        """Public holidays (Holiday integration calendars), if shops close then."""
        if not self.option(CONF_HOLIDAY_SHOPS_CLOSED):
            return set()
        registry = er.async_get(self.hass)
        return set().union(
            *(
                days
                for entity_id, days in self._calendar_days.items()
                if (entry := registry.async_get(entity_id)) and entry.platform == HOLIDAY_PLATFORM
            )
        )

    def is_meal_day(self, day: date) -> bool:
        return day.weekday() in self.meal_weekdays and day not in self.days_off

    def shopping_day(self, day: date) -> date:
        return planner.shopping_day(day, self.no_shopping_weekdays, self.shops_closed)

    def list_day(self, day: date) -> date:
        return planner.list_day(day, self.no_shopping_weekdays, self.shops_closed)

    @property
    def no_shopping_weekdays(self) -> list[int]:
        return _weekday_numbers(self.option(CONF_NO_SHOPPING_DAYS))

    @property
    def planner_options(self) -> planner.PlannerOptions:
        return planner.PlannerOptions(
            meal_mode=self.option(CONF_MEAL_MODE),
            soup_days=int(self.option(CONF_SOUP_DAYS)),
            soup_weekdays=frozenset(_weekday_numbers(self.option(CONF_SOUP_WEEKDAYS))),
            avoid_previous_week=bool(self.option(CONF_AVOID_PREVIOUS_WEEK)),
            meal_weekdays=frozenset(self.meal_weekdays),
            week_start=self.week_start,
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

    # -- days off --------------------------------------------------------

    async def async_refresh_days_off(self, until: date | None = None) -> None:
        """Read the all-day events of the days-off calendars.

        They are read from yesterday for ``DAYS_OFF_AHEAD`` days, or up to the
        last planned day or ``until`` when that is later (a day drawn far
        ahead). A calendar that cannot be read (e.g. not loaded yet) keeps the
        days read last time.
        """
        calendars = list(self.option(CONF_DAYS_OFF_CALENDARS) or [])
        self._calendar_days = {c: d for c, d in self._calendar_days.items() if c in calendars}
        if not calendars:
            return
        today = self.today()
        start = dt_util.start_of_local_day(today - timedelta(days=1))
        last = max(
            [date.fromisoformat(iso) for iso in self.plan] + ([until] if until else []),
            default=today,
        )
        days = max(DAYS_OFF_AHEAD, (last - today).days + 2)
        end = start + timedelta(days=days)
        for entity_id in calendars:
            try:
                response = await self.hass.services.async_call(
                    "calendar",
                    "get_events",
                    {"start_date_time": start, "end_date_time": end},
                    target={"entity_id": entity_id},
                    blocking=True,
                    return_response=True,
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Cannot read days off from %s: %s", entity_id, err)
                continue
            events = (response or {}).get(entity_id, {}).get("events", [])
            self._calendar_days[entity_id] = _all_day_dates(events)

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
        """A day is fixed from ``LOCK_TIME`` of the day its shopping list goes out.

        That is its shopping day, or the day before when it is bought in the
        morning of the lunch day. Until then the lunch can still change (the
        shopping list automation sends the list again); from then on it may
        already be bought.
        """
        now = dt_util.now()
        today = now.date()
        if day <= today:
            return True
        list_day = self.list_day(day)
        return list_day < today or (list_day == today and now.time() >= LOCK_TIME)

    def swappable(self, day: date) -> bool:
        """Whether the sides of the lunch on ``day`` can still be swapped."""
        meal = self.meal_for(day)
        return (
            meal is not None
            and any(p["category"] == planner.PROTEIN for p in meal["parts"])
            and not self.is_locked(day)
        )

    def _side(self, category: str, uid: str) -> dict[str, Any]:
        """A meal part from the database item ``uid`` of ``category``."""
        found_category, meal = self._find(uid)
        if found_category != category:
            raise HomeAssistantError(f"Meal {uid} is not in {category}")
        item = planner.Item(uid=meal["uid"], name=meal["name"], ingredients=tuple(meal["ingredients"]))
        return {
            "category": category,
            "uid": item.uid,
            "name": item.name,
            "ingredients": list(item.shopping_items()),
        }

    @callback
    def swap_sides(self, day: date, starch_uid: str, salad_uid: str | None) -> None:
        """Change the starch and the salad (or drop it) of a composed lunch."""
        meal = self.meal_for(day)
        if meal is None:
            raise HomeAssistantError(f"There is no lunch on {day}")
        if not any(p["category"] == planner.PROTEIN for p in meal["parts"]):
            raise HomeAssistantError(f"The lunch on {day} has no sides to swap")
        if self.is_locked(day):
            raise HomeAssistantError(f"{day} is already fixed: its shopping list is out")
        parts = [p for p in meal["parts"] if p["category"] not in (planner.STARCH, planner.SALAD)]
        parts.append(self._side(planner.STARCH, starch_uid))
        if salad_uid:
            parts.append(self._side(planner.SALAD, salad_uid))
        self.plan[day.isoformat()] = {**meal, "parts": parts}
        self.hass.bus.async_fire(EVENT_PLAN_UPDATED, self._plan_event([day], REASON_SWAP))
        self._changed()

    @callback
    def _draw(self, days: list[date], reason: str) -> list[date]:
        # A locked day keeps its meal; a future day with no meal can always get one.
        today = self.today()
        days = [
            d
            for d in days
            if d > today
            and self.is_meal_day(d)
            and (not self.is_locked(d) or d.isoformat() not in self.plan)
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

    def _plan_event(
        self, drawn: list[date], reason: str, week_of: date | None = None
    ) -> dict[str, Any]:
        """Event data, ready to be put into a notification by an automation.

        ``meals`` and ``summary`` cover every planned day from tomorrow to the
        end of the last drawn day's week (or of ``week_of``'s week), so a
        weekly draw also lists the lunches of the week drawn earlier.
        """
        week_end = planner.week_end(max(drawn) if drawn else week_of, self.week_start)
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

    def _rest_of_week(self) -> list[date]:
        days = planner.rest_of_week_days(self.today(), self.meal_weekdays, self.week_start)
        return [d for d in days if self.is_meal_day(d)]

    def _next_week(self) -> list[date]:
        days = planner.next_week_days(self.today(), self.meal_weekdays, self.week_start)
        return [d for d in days if self.is_meal_day(d)]

    async def async_redraw(self, day: date | None = None) -> list[date]:
        """Draw one day again, or all upcoming days that can still change."""
        await self.async_refresh_days_off(until=day)
        self._remove_days_off()
        if day is not None:
            if not self.is_meal_day(day):
                raise HomeAssistantError(f"{day} is not a meal day")
            if self.is_locked(day):
                raise HomeAssistantError(f"{day} is already fixed: its shopping list is out")
            return self._draw([day], REASON_REDRAW)
        days = self.upcoming_days()
        if not days:
            days = self._rest_of_week()
        if not [d for d in days if not self.is_locked(d)]:
            days = self._next_week()
        return self._draw(days, REASON_REDRAW)

    def _next_weekly_draw(self) -> datetime:
        """When the weekly draw plans the next week: still ahead, or missed."""
        start = planner.next_week_start(self.today(), self.week_start)
        draw_weekday = WEEKDAYS.index(self.option(CONF_DRAW_WEEKDAY))
        day = start - timedelta(days=7 - (draw_weekday - start.weekday()) % 7)
        hour, minute, second = _parse_time(self.option(CONF_DRAW_TIME))
        return dt_util.start_of_local_day(day).replace(hour=hour, minute=minute, second=second)

    @callback
    def async_ensure_plan(self) -> None:
        """Draw the next meal days when nothing is planned ahead.

        On the first start, or after Home Assistant was off at the weekly draw.
        The next week waits for its weekly draw while that is still ahead;
        lunches whose shopping list is due before it are drawn on their own.
        """
        today = self.today()
        if any(date.fromisoformat(iso) > today for iso in self.plan):
            return
        days = self._rest_of_week()
        if not [d for d in days if not self.is_locked(d)]:
            if dt_util.now() < self._next_weekly_draw():
                return
            days = self._next_week()
        self._draw(days, REASON_FIRST)

    @callback
    def async_weekly_draw(self) -> list[date]:
        """Fill in the next week; lunches drawn earlier for it stay.

        The event goes out also when nothing was left to draw, so the weekly
        plan is sent at the usual time.
        """
        days = self._next_week()
        if not days:
            return []
        drawn = self._draw([d for d in days if d.isoformat() not in self.plan], REASON_WEEKLY)
        if not drawn:
            self.hass.bus.async_fire(
                EVENT_PLAN_UPDATED, self._plan_event([], REASON_WEEKLY, week_of=days[0])
            )
        return drawn

    @callback
    def _remove_days_off(self) -> None:
        """Drop planned lunches on days that became days off, unless fixed."""
        today = self.today()
        days_off = self.days_off
        removed = [
            iso
            for iso in self.plan
            if (day := date.fromisoformat(iso)) > today
            and day in days_off
            and not self.is_locked(day)
        ]
        for iso in removed:
            del self.plan[iso]
        if removed:
            _LOGGER.debug("Removed lunches on days off: %s", removed)
            self._changed()

    @callback
    def _draw_missing(self) -> None:
        """Draw meals whose shopping list is due but which are not planned yet.

        E.g. when the weekly draw is set later than the first shopping day of
        the week. Runs at start-up and at midnight.
        """
        today = self.today()
        missing = []
        for offset in range(1, 9):
            day = today + timedelta(days=offset)
            if (
                self.is_meal_day(day)
                and day.isoformat() not in self.plan
                and self.list_day(day) <= today
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

    def lunch_times(self, meal: dict[str, Any]) -> tuple[datetime, datetime]:
        """Start and end of a lunch, in Home Assistant's time zone."""
        hour, minute, _ = _parse_time(str(self.option(CONF_LUNCH_TIME)))
        start = datetime.combine(
            date.fromisoformat(meal["date"]),
            time(hour, minute),
            tzinfo=dt_util.get_default_time_zone(),
        )
        return start, start + timedelta(minutes=int(self.option(CONF_LUNCH_DURATION)))

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
            meals = planner.meals_to_buy_on(
                self.plan, day, self.no_shopping_weekdays, self.shops_closed
            )
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
        # Lunches whose shopping list goes out today become fixed.
        self._unsubs.append(
            async_track_time_change(
                self.hass,
                self._on_lock_time,
                hour=LOCK_TIME.hour,
                minute=LOCK_TIME.minute,
                second=LOCK_TIME.second,
            )
        )
        # Calendars of other integrations (days off) may load after this one.
        self._unsubs.append(async_at_started(self.hass, self._async_on_started))

    async def _async_on_started(self, _hass: HomeAssistant) -> None:
        await self.async_refresh_days_off()
        self._remove_days_off()
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
            self.entry.async_create_task(self.hass, self._async_weekly_draw_fresh())

    async def _async_weekly_draw_fresh(self) -> None:
        await self.async_refresh_days_off()
        self._remove_days_off()
        self.async_weekly_draw()

    @callback
    def _on_lock_time(self, _now: datetime) -> None:
        for update in list(self._listeners):
            update()

    @callback
    def _on_midnight(self, _now: datetime) -> None:
        self.entry.async_create_task(self.hass, self._async_midnight())

    async def _async_midnight(self) -> None:
        await self.async_refresh_days_off()
        self._remove_days_off()
        self._draw_missing()
        for update in list(self._listeners):
            update()
