"""Tests for the pure meal-drawing logic (no Home Assistant needed)."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
import importlib.util
from pathlib import Path
import random
import sys

import pytest

# Load planner.py directly, so these tests run without Home Assistant installed.
_PATH = Path(__file__).parents[1] / "custom_components" / "lunch_planner" / "planner.py"
_SPEC = importlib.util.spec_from_file_location("lunch_planner_planner", _PATH)
planner = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = planner
_SPEC.loader.exec_module(planner)

Item = planner.Item
PlannerOptions = planner.PlannerOptions

MONDAY = date(2026, 11, 16)
WEEK = [MONDAY + timedelta(days=i) for i in range(5)]


def item(uid: str, ingredients: tuple[str, ...] = (), season=None) -> Item:
    return Item(uid=uid, name=uid, ingredients=ingredients, season=season)


@pytest.fixture
def catalog():
    """The example database from the project brief."""
    return {
        planner.SOUP: [item("cauliflower"), item("mushroom"), item("beetroot", season=(5, 7))],
        planner.DISH: [item("stir-fry vegetables"), item("spaghetti")],
        planner.PROTEIN: [item("salmon fillet"), item("pork chop")],
        planner.STARCH: [item("boiled potatoes"), item("fries"), item("roast potatoes")],
        planner.SALAD: [
            item("cucumber salad"),
            item("mixed leaves"),
            item("sauerkraut slaw"),
            item("carrots and peas"),
        ],
    }


def names(meal) -> list[str]:
    return [p["name"] for p in meal["parts"]]


def uids_by_day(plan, category=None):
    return {
        iso: [p["uid"] for p in meal["parts"] if category in (None, p["category"])]
        for iso, meal in plan.items()
    }


# --- parsing -------------------------------------------------------------


def test_parse_item_ingredients_and_season():
    parsed = planner.parse_item(
        "1", " Botwinkowa ", "botwinka, ziemniaki\n- śmietana\n# komentarz\nsezon: 5-7\nbotwinka"
    )
    assert parsed.name == "Botwinkowa"
    assert parsed.ingredients == ("botwinka", "ziemniaki", "śmietana")
    assert parsed.season == (5, 7)


def test_parse_item_without_description_buys_the_name():
    parsed = planner.parse_item("1", "Kalafiorowa", None)
    assert parsed.ingredients == ()
    assert parsed.shopping_items() == ("Kalafiorowa",)


def test_invalid_season_is_ignored():
    assert planner.parse_item("1", "x", "season: 0-13").season is None


@pytest.mark.parametrize(
    ("season", "month", "expected"),
    [((5, 7), 6, True), ((5, 7), 11, False), ((11, 2), 12, True), ((11, 2), 1, True), ((11, 2), 6, False)],
)
def test_in_season(season, month, expected):
    assert item("x", season=season).in_season(date(2026, month, 10)) is expected


# --- drawing -------------------------------------------------------------


def test_soup_or_main_gives_exactly_one_kind_per_day(catalog):
    plan = planner.plan_days(WEEK, catalog, PlannerOptions(), rng=random.Random(1))
    assert len(plan) == 5
    for meal in plan.values():
        categories = {p["category"] for p in meal["parts"]}
        assert (categories == {planner.SOUP}) or (planner.SOUP not in categories)


@pytest.mark.parametrize("share", [0, 40, 60, 100])
def test_soup_share_sets_the_number_of_soup_days(catalog, share):
    plan = planner.plan_days(WEEK, catalog, PlannerOptions(soup_share=share), rng=random.Random(2))
    soup_days = sum(1 for m in plan.values() if m["parts"][0]["category"] == planner.SOUP)
    assert soup_days == round(5 * share / 100)


def test_soup_and_main_mode(catalog):
    plan = planner.plan_days(
        WEEK, catalog, PlannerOptions(meal_mode=planner.MODE_SOUP_AND_MAIN), rng=random.Random(3)
    )
    for meal in plan.values():
        assert meal["parts"][0]["category"] == planner.SOUP
        assert len(meal["parts"]) >= 2


def test_composed_main_has_starch_and_salad(catalog):
    options = PlannerOptions(meal_mode=planner.MODE_MAIN_ONLY)
    for seed in range(30):
        plan = planner.plan_days(WEEK, catalog, options, rng=random.Random(seed))
        for meal in plan.values():
            categories = [p["category"] for p in meal["parts"]]
            assert categories in ([planner.DISH], [planner.PROTEIN, planner.STARCH, planner.SALAD])


def test_out_of_season_soup_is_never_drawn(catalog):
    options = PlannerOptions(meal_mode=planner.MODE_SOUP_ONLY)
    for seed in range(30):
        plan = planner.plan_days(WEEK, catalog, options, rng=random.Random(seed))
        assert all("beetroot" not in names(m) for m in plan.values())


def test_in_season_soup_can_be_drawn(catalog):
    june_week = [date(2026, 6, 1) + timedelta(days=i) for i in range(5)]
    options = PlannerOptions(meal_mode=planner.MODE_SOUP_ONLY)
    plan = planner.plan_days(june_week, catalog, options, rng=random.Random(0))
    assert Counter(n for m in plan.values() for n in names(m))["beetroot"] >= 1


def test_no_item_repeats_on_consecutive_days(catalog):
    for seed in range(50):
        for mode in planner.MEAL_MODES:
            plan = planner.plan_days(WEEK, catalog, PlannerOptions(meal_mode=mode), rng=random.Random(seed))
            days = sorted(plan)
            for a, b in zip(days, days[1:], strict=False):
                assert not set(uids_by_day(plan)[a]) & set(uids_by_day(plan)[b]), (seed, mode, plan)


def test_mains_do_not_repeat_within_week_when_enough_options(catalog):
    options = PlannerOptions(meal_mode=planner.MODE_MAIN_ONLY)
    for seed in range(50):
        plan = planner.plan_days(WEEK[:4], catalog, options, rng=random.Random(seed))
        mains = [
            p["uid"] for m in plan.values() for p in m["parts"] if p["category"] in (planner.DISH, planner.PROTEIN)
        ]
        assert len(mains) == len(set(mains)), (seed, mains)


def test_previous_week_is_avoided_when_possible(catalog):
    options = PlannerOptions(meal_mode=planner.MODE_SOUP_ONLY)
    two_soups = {planner.SOUP: catalog[planner.SOUP][:2] + [item("tomato")]}
    last_friday = (MONDAY - timedelta(days=3)).isoformat()
    last_thursday = (MONDAY - timedelta(days=4)).isoformat()
    history = {
        last_thursday: {"date": last_thursday, "parts": [{"category": "soup", "uid": "tomato", "name": "tomato"}]},
        last_friday: {"date": last_friday, "parts": [{"category": "soup", "uid": "mushroom", "name": "mushroom"}]},
    }
    for seed in range(30):
        plan = planner.plan_days([MONDAY], two_soups, options, history, random.Random(seed))
        assert names(plan[MONDAY.isoformat()]) == ["cauliflower"]


def test_avoid_previous_week_can_be_switched_off(catalog):
    options = PlannerOptions(meal_mode=planner.MODE_SOUP_ONLY, avoid_previous_week=False)
    soups = {planner.SOUP: catalog[planner.SOUP][:2]}
    old = (MONDAY - timedelta(days=10)).isoformat()
    history = {old: {"date": old, "parts": [{"category": "soup", "uid": "mushroom", "name": "mushroom"}]}}
    seen = {
        names(planner.plan_days([MONDAY], soups, options, history, random.Random(s))[MONDAY.isoformat()])[0]
        for s in range(40)
    }
    assert seen == {"cauliflower", "mushroom"}


def test_redrawing_a_day_avoids_its_neighbours(catalog):
    options = PlannerOptions(meal_mode=planner.MODE_SOUP_ONLY)
    plan = planner.plan_days(WEEK, catalog, options, rng=random.Random(5))
    middle = WEEK[2]
    for seed in range(20):
        redrawn = planner.plan_days([middle], catalog, options, plan, random.Random(seed))
        neighbours = set(uids_by_day(plan)[WEEK[1].isoformat()]) | set(uids_by_day(plan)[WEEK[3].isoformat()])
        assert not set(uids_by_day(redrawn)[middle.isoformat()]) & neighbours


def test_fallbacks_for_missing_categories():
    only_soup = {planner.SOUP: [item("a"), item("b")]}
    plan = planner.plan_days(WEEK, only_soup, PlannerOptions(meal_mode=planner.MODE_MAIN_ONLY), rng=random.Random(0))
    assert all(m["parts"][0]["category"] == planner.SOUP for m in plan.values())

    protein_without_starch = {planner.PROTEIN: [item("chop")], planner.SOUP: [item("a")]}
    plan = planner.plan_days(WEEK, protein_without_starch, PlannerOptions(meal_mode=planner.MODE_MAIN_ONLY))
    assert all(names(m) == ["a"] for m in plan.values())

    assert planner.plan_days(WEEK, {}, PlannerOptions()) == {}


def test_composed_main_without_salads():
    catalog = {planner.PROTEIN: [item("chop")], planner.STARCH: [item("potatoes")]}
    plan = planner.plan_days([MONDAY], catalog, PlannerOptions(meal_mode=planner.MODE_MAIN_ONLY))
    assert names(plan[MONDAY.isoformat()]) == ["chop", "potatoes"]


# --- titles and shopping ---------------------------------------------------


def test_meal_title():
    meal = {
        "parts": [
            {"category": "soup", "name": "Grzybowa"},
            {"category": "protein", "name": "Schabowy"},
            {"category": "starch", "name": "Ziemniaki"},
        ]
    }
    assert planner.meal_title(meal) == "Grzybowa + Schabowy, Ziemniaki"


@pytest.mark.parametrize(
    ("parts", "polish", "english"),
    [
        ([("soup", "Grzybowa")], "Zupa grzybowa", "Grzybowa soup"),
        ([("soup", "Zupa pomidorowa")], "Zupa pomidorowa", "Zupa pomidorowa soup"),
        ([("soup", "Tomato soup")], "Zupa tomato soup", "Tomato soup"),
        ([("dish", "Warzywa na patelnię")], "Warzywa na patelnię", "Warzywa na patelnię"),
        (
            [("protein", "Kotlet schabowy"), ("starch", "Frytki"), ("salad", "Mizeria")],
            "Kotlet schabowy, frytki, mizeria",
            "Kotlet schabowy, frytki, mizeria",
        ),
        ([("soup", "Grzybowa"), ("dish", "BBQ wings")], "Zupa grzybowa + BBQ wings", "Grzybowa soup + BBQ wings"),
    ],
)
def test_meal_text(parts, polish, english):
    meal = {"parts": [{"category": c, "name": n} for c, n in parts]}
    assert planner.meal_text(meal, "zupa {name}", "zup") == polish
    assert planner.meal_text(meal) == english
    assert planner.meal_text(meal, "zupa {name}", "zup", capitalize=False) == polish[:1].lower() + polish[1:]


def test_shopping_items_are_deduplicated():
    meals = [
        {"parts": [{"name": "A", "ingredients": ["Ziemniaki", "masło"]}]},
        {"parts": [{"name": "B", "ingredients": ["ziemniaki", "koperek"]}, {"name": "C", "ingredients": []}]},
    ]
    assert planner.meal_shopping_items(meals) == ["Ziemniaki", "masło", "koperek", "C"]


def test_shopping_day_skips_closed_days():
    sunday = 6
    assert planner.shopping_day(MONDAY, [sunday]) == MONDAY - timedelta(days=2)  # Saturday
    assert planner.shopping_day(MONDAY + timedelta(days=1), [sunday]) == MONDAY
    assert planner.shopping_day(MONDAY, []) == MONDAY - timedelta(days=1)


def test_long_break_moves_shopping_to_the_lunch_morning():
    sunday = 6
    # Easter 2027: Sunday 28.03 and Monday 29.03 closed. Tuesday's lunch would
    # be bought on Saturday, 3 days ahead: it is bought on Tuesday morning.
    easter_monday = date(2027, 3, 29)
    tuesday = date(2027, 3, 30)
    assert planner.shopping_day(tuesday, [sunday], [easter_monday]) == tuesday
    assert planner.list_day(tuesday, [sunday], [easter_monday]) == easter_monday
    # Two days ahead is fine: Monday's lunch is bought on Saturday.
    assert planner.shopping_day(MONDAY, [sunday]) == MONDAY - timedelta(days=2)
    assert planner.list_day(MONDAY, [sunday]) == MONDAY - timedelta(days=2)
    # Christmas 2026: 24-26.12 holidays, 27.12 Sunday.
    christmas = [date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 26)]
    monday = date(2026, 12, 28)
    assert planner.shopping_day(monday, [sunday], christmas) == monday
    assert planner.list_day(monday, [sunday], christmas) == date(2026, 12, 27)
    # The lunch day itself is closed too: the last open day it is.
    assert planner.shopping_day(date(2026, 12, 26), [sunday], christmas) == date(2026, 12, 23)
    # Same-day shopping is on that day's list.
    plan = {monday.isoformat(): {"date": monday.isoformat(), "parts": []}}
    assert planner.meals_to_buy_on(plan, monday, [sunday], christmas) == [plan[monday.isoformat()]]
    assert planner.meals_to_buy_on(plan, date(2026, 12, 23), [sunday], christmas) == []


def test_meals_to_buy_on_saturday_covers_monday():
    plan = {d.isoformat(): {"date": d.isoformat(), "parts": []} for d in WEEK}
    saturday = MONDAY - timedelta(days=2)
    assert [m["date"] for m in planner.meals_to_buy_on(plan, saturday, [6])] == [MONDAY.isoformat()]
    assert planner.meals_to_buy_on(plan, saturday + timedelta(days=1), [6]) == []
    assert [m["date"] for m in planner.meals_to_buy_on(plan, MONDAY, [6])] == [WEEK[1].isoformat()]


def test_week_helpers():
    wednesday = date(2026, 11, 11)
    weekdays = range(5)
    assert planner.next_week_days(wednesday, weekdays) == WEEK
    assert planner.next_week_days(MONDAY, weekdays)[0] == MONDAY + timedelta(days=7)
    assert planner.rest_of_week_days(wednesday, weekdays) == [date(2026, 11, 12), date(2026, 11, 13)]
    assert planner.rest_of_week_days(date(2026, 11, 13), weekdays) == []
