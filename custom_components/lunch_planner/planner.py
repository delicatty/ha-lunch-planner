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
    soup_share: int = 50
    avoid_previous_week: bool = True


def meal_title(meal: Mapping[str, Any]) -> str:
    """Short one-line description of a meal, e.g. ``Soup + Chop, potatoes, salad``."""
    soups = [p["name"] for p in meal.get("parts", []) if p["category"] == SOUP]
    mains = [p["name"] for p in meal.get("parts", []) if p["category"] != SOUP]
    groups = [", ".join(soups)] if soups else []
    if mains:
        groups.append(", ".join(mains))
    return " + ".join(groups)


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


def _meal_kinds(count: int, options: PlannerOptions, rng: random.Random) -> list[set[str]]:
    """Decide for each day whether it gets a soup, a main course or both."""
    mode = options.meal_mode
    if mode == MODE_SOUP_ONLY:
        return [{_KIND_SOUP} for _ in range(count)]
    if mode == MODE_MAIN_ONLY:
        return [{_KIND_MAIN} for _ in range(count)]
    if mode == MODE_SOUP_AND_MAIN:
        return [{_KIND_SOUP, _KIND_MAIN} for _ in range(count)]
    share = min(max(options.soup_share, 0), 100)
    soups = round(count * share / 100)
    kinds = [{_KIND_SOUP}] * soups + [{_KIND_MAIN}] * (count - soups)
    rng.shuffle(kinds)
    return [set(k) for k in kinds]


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
    days = sorted(set(days))
    picker = _Picker(history or {}, set(days), options, rng)
    kinds = _meal_kinds(len(days), options, rng)
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


def shopping_day(meal_day: date, no_shopping_weekdays: Iterable[int]) -> date:
    """Day on which to buy for ``meal_day``: the latest earlier shopping day."""
    closed = set(no_shopping_weekdays)
    day = meal_day - timedelta(days=1)
    for _ in range(7):
        if day.weekday() not in closed:
            return day
        day -= timedelta(days=1)
    return meal_day - timedelta(days=1)  # every day closed: buy the day before


def meals_to_buy_on(
    plan: Mapping[str, Mapping[str, Any]],
    day: date,
    no_shopping_weekdays: Iterable[int],
) -> list[Mapping[str, Any]]:
    """Planned meals whose shopping falls on ``day``, in date order."""
    closed = list(no_shopping_weekdays)
    result = []
    for iso in sorted(plan):
        meal_day = date.fromisoformat(iso)
        if meal_day > day and shopping_day(meal_day, closed) == day:
            result.append(plan[iso])
    return result


def next_week_days(today: date, meal_weekdays: Iterable[int]) -> list[date]:
    """Meal days of the week that starts on the first Monday after ``today``."""
    weekdays = set(meal_weekdays)
    monday = today + timedelta(days=7 - today.weekday())
    return [monday + timedelta(days=i) for i in range(7) if i in weekdays]


def rest_of_week_days(today: date, meal_weekdays: Iterable[int]) -> list[date]:
    """Meal days from tomorrow until Sunday of the current week."""
    weekdays = set(meal_weekdays)
    return [
        today + timedelta(days=i)
        for i in range(1, 7 - today.weekday())
        if (today + timedelta(days=i)).weekday() in weekdays
    ]
