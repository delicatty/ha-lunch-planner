"""Meal drawing logic for Lunch Planner.

This module has no Home Assistant imports, so it can be unit-tested on its own.

Data model
----------
The meal database is split into five categories:

* ``soup``     - a soup, served as the whole meal or before a main course,
* ``dish``     - a complete main course that needs nothing else (e.g. spaghetti),
* ``protein``  - the main part of a composed main course (e.g. pork chop),
* ``starch``   - the starchy side of a composed main course (e.g. potatoes),
* ``salad``    - the salad / vegetable side of a composed main course.

Every item has a name and a free-text description. Each description line
(or comma-separated part of a line) is one thing to buy. A line such as
``season: 5-7`` (or ``sezon: 5-7``) limits the item to those months.
Lines starting with ``#`` are comments.

A planned meal is a plain dict, so it can be stored as JSON::

    {"date": "2026-11-16",
     "parts": [{"category": "protein", "uid": "...", "name": "Pork chop",
                "ingredients": ["pork loin", "breadcrumbs"]}, ...]}
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
import random
import re
from typing import Any

SOUP = "soup"
DISH = "dish"
PROTEIN = "protein"
STARCH = "starch"
SALAD = "salad"
CATEGORIES = (SOUP, DISH, PROTEIN, STARCH, SALAD)

MODE_SOUP_OR_MAIN = "soup_or_main"
MODE_SOUP_AND_MAIN = "soup_and_main"
MODE_SOUP_ONLY = "soup_only"
MODE_MAIN_ONLY = "main_only"
MEAL_MODES = (MODE_SOUP_OR_MAIN, MODE_SOUP_AND_MAIN, MODE_SOUP_ONLY, MODE_MAIN_ONLY)

_KIND_SOUP = "soup"
_KIND_MAIN = "main"

# How strongly an item is avoided when it was used N days away from the
# planned day. Yesterday/tomorrow is avoided hardest, the same week next,
# then the neighbouring week (only with avoid_previous_week).
_PENALTY_ADJACENT = 100
_PENALTY_SAME_WEEK = 10
_PENALTY_NEAR_WEEK = 1

_SEASON_RE = re.compile(
    r"^\s*(?:season|sezon)\s*[:=]?\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s*$", re.IGNORECASE
)


@dataclass(frozen=True)
class Item:
    """One entry of the meal database."""

    uid: str
    name: str
    ingredients: tuple[str, ...] = ()
    season: tuple[int, int] | None = None

    def in_season(self, day: date) -> bool:
        """Return True when the item may be served on ``day``."""
        if self.season is None:
            return True
        start, end = self.season
        month = day.month
        if start <= end:
            return start <= month <= end
        return month >= start or month <= end  # season wraps over new year

    def shopping_items(self) -> tuple[str, ...]:
        """Things to buy for this item; the name when nothing is listed."""
        return self.ingredients or (self.name,)


def parse_item(uid: str, name: str, description: str | None) -> Item:
    """Build an Item from a to-do item's summary and description."""
    ingredients: list[str] = []
    season: tuple[int, int] | None = None
    for raw_line in (description or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SEASON_RE.match(line)
        if match:
            start, end = int(match[1]), int(match[2])
            if 1 <= start <= 12 and 1 <= end <= 12:
                season = (start, end)
            continue
        for part in line.split(","):
            part = part.strip().lstrip("-•* ").strip()
            if part and part not in ingredients:
                ingredients.append(part)
    return Item(uid=uid, name=name.strip(), ingredients=tuple(ingredients), season=season)


@dataclass(frozen=True)
class PlannerOptions:
    """Options that change how meals are drawn."""

    meal_mode: str = MODE_SOUP_OR_MAIN
    # With MODE_SOUP_OR_MAIN: soups per week, and the weekdays that get them first.
    soup_days: int = 2
    soup_weekdays: frozenset[int] = frozenset({0})
    avoid_previous_week: bool = True
    # Weekdays (0 Monday ... 6 Sunday) that have a lunch, and the first day of
    # the week. The soups of a week are shared out over all its lunch days,
    # also the ones off or not drawn now.
    meal_weekdays: frozenset[int] = frozenset(range(5))
    week_start: int = 0


def meal_title(meal: Mapping[str, Any]) -> str:
    """Short one-line description of a meal, e.g. ``Soup + Chop, potatoes, salad``."""
    soups = [p["name"] for p in meal.get("parts", []) if p["category"] == SOUP]
    mains = [p["name"] for p in meal.get("parts", []) if p["category"] != SOUP]
    groups = [", ".join(soups)] if soups else []
    if mains:
        groups.append(", ".join(mains))
    return " + ".join(groups)


def _lower_first(name: str) -> str:
    """``Grzybowa`` -> ``grzybowa``, but keep acronyms such as ``BBQ``."""
    if len(name) > 1 and name[:2].isupper():
        return name
    return name[:1].lower() + name[1:]


def meal_text(
    meal: Mapping[str, Any],
    soup_format: str = "{name} soup",
    soup_word: str = "soup",
    capitalize: bool = True,
) -> str:
    """Natural description of a meal, e.g. ``Mushroom soup`` or ``Pork chop, fries``.

    ``soup_format`` turns a soup's name into a phrase (``zupa {name}`` in
    Polish), unless the name already contains ``soup_word``.
    """
    soups = []
    mains = []
    for part in meal.get("parts", []):
        name = _lower_first(part["name"].strip())
        if part["category"] == SOUP:
            if soup_word.casefold() not in name.casefold():
                name = soup_format.format(name=name)
            soups.append(name)
        else:
            mains.append(name)
    groups = [", ".join(soups)] if soups else []
    if mains:
        groups.append(", ".join(mains))
    text = " + ".join(groups)
    return text[:1].upper() + text[1:] if capitalize else text


def meal_shopping_items(meals: Iterable[Mapping[str, Any]]) -> list[str]:
    """Deduplicated things to buy for the given meals, in serving order."""
    result: list[str] = []
    seen: set[str] = set()
    for meal in meals:
        for part in meal.get("parts", []):
            for ingredient in part.get("ingredients") or [part["name"]]:
                key = ingredient.casefold()
                if key not in seen:
                    seen.add(key)
                    result.append(ingredient)
    return result


def _part(category: str, item: Item) -> dict[str, Any]:
    return {
        "category": category,
        "uid": item.uid,
        "name": item.name,
        "ingredients": list(item.shopping_items()),
    }


class _Picker:
    """Chooses items so that repeats are as rare and as far apart as possible."""

    def __init__(
        self,
        history: Mapping[str, Mapping[str, Any]],
        replanned: set[date],
        options: PlannerOptions,
        rng: random.Random,
    ) -> None:
        self._options = options
        self._rng = rng
        # (date, uid) of every meal part that stays in place
        self._used: list[tuple[date, str]] = []
        for iso, meal in history.items():
            day = date.fromisoformat(iso)
            if day in replanned:
                continue
            for part in meal.get("parts", []):
                self._used.append((day, part["uid"]))

    def add(self, day: date, uid: str) -> None:
        self._used.append((day, uid))

    def _score(self, uid: str, day: date) -> int:
        score = 0
        for used_day, used_uid in self._used:
            if used_uid != uid:
                continue
            distance = abs((used_day - day).days)
            if distance <= 1:
                score += _PENALTY_ADJACENT
            elif distance <= 6:
                score += _PENALTY_SAME_WEEK
            elif distance <= 13 and self._options.avoid_previous_week:
                score += _PENALTY_NEAR_WEEK
        return score

    def pick(self, candidates: list[Any], day: date, uid_of=lambda c: c.uid) -> Any | None:
        """Random choice among the candidates with the lowest repeat score."""
        if not candidates:
            return None
        scored = [(self._score(uid_of(c), day), c) for c in candidates]
        best = min(score for score, _ in scored)
        return self._rng.choice([c for score, c in scored if score == best])


def _has_soup(meal: Mapping[str, Any] | None) -> bool:
    return bool(meal) and any(p["category"] == SOUP for p in meal.get("parts", []))


def _soup_days(
    days: list[date],
    history: Mapping[str, Mapping[str, Any]],
    options: PlannerOptions,
    rng: random.Random,
) -> set[date]:
    """Days among ``days`` that get a soup, with one course a day.

    Each week has ``soup_days`` soups. Meals that stay in the plan keep theirs;
    the rest are shared out over the week's other lunch days: the days being
    drawn and the lunch days without a meal (off, or past before the plan
    started). Preferred weekdays come first. A soup that lands on a day
    without a meal is lost, so days off take soups away in proportion.
    """
    drawn = set(days)
    starts = sorted({d - timedelta(days=(d.weekday() - options.week_start) % 7) for d in days})
    result: set[date] = set()
    for start in starts:
        week = [start + timedelta(days=i) for i in range(7)]
        kept = [d for d in week if d not in drawn and d.isoformat() in history]
        kept_soups = sum(1 for d in kept if _has_soup(history[d.isoformat()]))
        slots = [
            d
            for d in week
            if d in drawn or (d.weekday() in options.meal_weekdays and d not in kept)
        ]
        left = max(min(options.soup_days, 7) - kept_soups, 0)
        preferred = [d for d in slots if d.weekday() in options.soup_weekdays]
        others = [d for d in slots if d.weekday() not in options.soup_weekdays]
        chosen = rng.sample(preferred, min(left, len(preferred)))
        chosen += rng.sample(others, min(left - len(chosen), len(others)))
        result.update(d for d in chosen if d in drawn)
    return result


def _meal_kinds(
    days: list[date],
    history: Mapping[str, Mapping[str, Any]],
    options: PlannerOptions,
    rng: random.Random,
) -> list[set[str]]:
    """Decide for each day whether it gets a soup, a main course or both."""
    mode = options.meal_mode
    if mode == MODE_SOUP_ONLY:
        return [{_KIND_SOUP} for _ in days]
    if mode == MODE_MAIN_ONLY:
        return [{_KIND_MAIN} for _ in days]
    if mode == MODE_SOUP_AND_MAIN:
        return [{_KIND_SOUP, _KIND_MAIN} for _ in days]
    soups = _soup_days(days, history, options, rng)
    return [{_KIND_SOUP} if d in soups else {_KIND_MAIN} for d in days]


def plan_days(
    days: Iterable[date],
    catalog: Mapping[str, list[Item]],
    options: PlannerOptions,
    history: Mapping[str, Mapping[str, Any]] | None = None,
    rng: random.Random | None = None,
) -> dict[str, dict[str, Any]]:
    """Draw a meal for each of ``days``.

    ``history`` holds already planned or past meals keyed by ISO date. Meals on
    the days being drawn are ignored; all the others count as recent use, so
    the draw avoids repeating them nearby.

    A day for which nothing can be drawn (empty database) is left out.
    """
    rng = rng or random.Random()
    history = history or {}
    days = sorted(set(days))
    picker = _Picker(history, set(days), options, rng)
    kinds = _meal_kinds(days, history, options, rng)
    plan: dict[str, dict[str, Any]] = {}

    for day, wanted in zip(days, kinds, strict=True):
        def available(category: str, day: date = day) -> list[Item]:
            return [item for item in catalog.get(category, []) if item.in_season(day)]

        soups = available(SOUP)
        dishes = available(DISH)
        proteins = available(PROTEIN)
        starches = available(STARCH)
        salads = available(SALAD)
        can_compose = bool(proteins and starches)
        has_main = bool(dishes) or can_compose

        # Fall back to whatever the database can offer.
        if _KIND_SOUP in wanted and not soups:
            wanted = (wanted - {_KIND_SOUP}) | {_KIND_MAIN}
        if _KIND_MAIN in wanted and not has_main:
            wanted = (wanted - {_KIND_MAIN}) | ({_KIND_SOUP} if soups else set())
        if not wanted:
            continue

        parts: list[dict[str, Any]] = []
        if _KIND_SOUP in wanted:
            soup = picker.pick(soups, day)
            picker.add(day, soup.uid)
            parts.append(_part(SOUP, soup))

        if _KIND_MAIN in wanted:
            # Complete dishes and proteins compete in one pool, so each of
            # them is equally likely regardless of how the main is built.
            pool = [(DISH, d) for d in dishes]
            if can_compose:
                pool += [(PROTEIN, p) for p in proteins]
            category, main = picker.pick(pool, day, uid_of=lambda c: c[1].uid)
            picker.add(day, main.uid)
            parts.append(_part(category, main))
            if category == PROTEIN:
                starch = picker.pick(starches, day)
                picker.add(day, starch.uid)
                parts.append(_part(STARCH, starch))
                salad = picker.pick(salads, day)
                if salad is not None:
                    picker.add(day, salad.uid)
                    parts.append(_part(SALAD, salad))

        plan[day.isoformat()] = {"date": day.isoformat(), "parts": parts}

    return plan


# Buying more than this many days before a lunch is too early: then it is
# bought on the morning of the lunch day instead.
MAX_DAYS_AHEAD = 2


def _closed(day: date, weekdays: set[int], dates: set[date]) -> bool:
    return day.weekday() in weekdays or day in dates


def shopping_day(
    meal_day: date,
    no_shopping_weekdays: Iterable[int],
    closed_dates: Iterable[date] = (),
) -> date:
    """Day on which to buy for ``meal_day``.

    Normally the latest open day before it. When that is more than
    ``MAX_DAYS_AHEAD`` days before (e.g. after Easter), the lunch day itself,
    in the morning, unless shops are closed on it too.
    """
    weekdays = set(no_shopping_weekdays)
    dates = set(closed_dates)
    day = meal_day - timedelta(days=1)
    for _ in range(14):
        if not _closed(day, weekdays, dates):
            break
        day -= timedelta(days=1)
    else:
        return meal_day - timedelta(days=1)  # every day closed: buy the day before
    if (meal_day - day).days > MAX_DAYS_AHEAD and not _closed(meal_day, weekdays, dates):
        return meal_day
    return day


def list_day(
    meal_day: date,
    no_shopping_weekdays: Iterable[int],
    closed_dates: Iterable[date] = (),
) -> date:
    """Day on which the shopping list for ``meal_day`` goes out.

    The shopping day, or the evening before when shopping is in the morning
    of the lunch day.
    """
    day = shopping_day(meal_day, no_shopping_weekdays, closed_dates)
    return day if day < meal_day else meal_day - timedelta(days=1)


def meals_to_buy_on(
    plan: Mapping[str, Mapping[str, Any]],
    day: date,
    no_shopping_weekdays: Iterable[int],
    closed_dates: Iterable[date] = (),
) -> list[Mapping[str, Any]]:
    """Planned meals whose shopping falls on ``day``, in date order."""
    weekdays = list(no_shopping_weekdays)
    dates = list(closed_dates)
    result = []
    for iso in sorted(plan):
        meal_day = date.fromisoformat(iso)
        if meal_day >= day and shopping_day(meal_day, weekdays, dates) == day:
            result.append(plan[iso])
    return result


def _days_to_next_week(today: date, week_start: int) -> int:
    """Days from ``today`` to the start of the next week (1-7)."""
    return (week_start - today.weekday()) % 7 or 7


def next_week_start(today: date, week_start: int = 0) -> date:
    """First ``week_start`` day after ``today`` (0 Monday ... 6 Sunday)."""
    return today + timedelta(days=_days_to_next_week(today, week_start))


def next_week_days(today: date, meal_weekdays: Iterable[int], week_start: int = 0) -> list[date]:
    """Meal days of the week that starts on the first ``week_start`` day after ``today``.

    ``week_start`` is a weekday number: 0 Monday ... 6 Sunday.
    """
    weekdays = set(meal_weekdays)
    start = next_week_start(today, week_start)
    days = [start + timedelta(days=i) for i in range(7)]
    return [d for d in days if d.weekday() in weekdays]


def rest_of_week_days(today: date, meal_weekdays: Iterable[int], week_start: int = 0) -> list[date]:
    """Meal days from tomorrow until the last day of the current week."""
    weekdays = set(meal_weekdays)
    return [
        today + timedelta(days=i)
        for i in range(1, _days_to_next_week(today, week_start))
        if (today + timedelta(days=i)).weekday() in weekdays
    ]


def week_end(day: date, week_start: int = 0) -> date:
    """Last day of the week that ``day`` is in."""
    return day + timedelta(days=(week_start - day.weekday() - 1) % 7)
