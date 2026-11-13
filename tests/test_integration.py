"""Tests of Lunch Planner running inside Home Assistant."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    MockPlatform,
    async_fire_time_changed,
    mock_integration,
    mock_platform,
)

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.lunch_planner.const import DEFAULT_OPTIONS, DOMAIN, default_week_start

WEDNESDAY_NOON = "2026-11-11 12:00:00"


def local(text: str) -> datetime:
    return dt_util.parse_datetime(text).replace(tzinfo=dt_util.get_default_time_zone())


@pytest.fixture
async def hass_pl(hass: HomeAssistant) -> HomeAssistant:
    await hass.config.async_set_time_zone("Europe/Warsaw")
    hass.config.language = "pl"
    return hass


def make_entry(**options) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Obiady",
        version=1,
        minor_version=3,
        options={**DEFAULT_OPTIONS, **options},
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def entity(hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, (domain, key)
    return entity_id


async def add_items(hass: HomeAssistant, entry: MockConfigEntry, category: str, *names: str) -> None:
    for name in names:
        await hass.services.async_call(
            DOMAIN,
            "add_meal",
            {"config_entry_id": entry.entry_id, "category": category, "name": name},
            blocking=True,
        )


async def fill_database(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await add_items(hass, entry, "soup", "Kalafiorowa", "Grzybowa")
    await add_items(hass, entry, "dish", "Warzywa na patelnię", "Spaghetti")
    await add_items(hass, entry, "protein", "Filet z łososia", "Kotlet schabowy")
    await add_items(hass, entry, "starch", "Ziemniaki z wody", "Frytki", "Pieczone ziemniaki")
    await add_items(hass, entry, "salad", "Mizeria", "Miks sałat", "Surówka z kapusty", "Marchewka z groszkiem")


async def test_config_flow(hass_pl: HomeAssistant) -> None:
    hass = hass_pl
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Obiady"})
    assert result["step_id"] == "settings"

    bad = {**DEFAULT_OPTIONS, "workdays": []}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], bad)
    assert result["errors"] == {"workdays": "no_workdays"}
    every_day_worked = {**DEFAULT_OPTIONS, "meal_schedule": "weekends",
                        "workdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], every_day_worked)
    assert result["errors"] == {"workdays": "no_weekend_days"}

    # Weekends have 2 lunch days: 3 soups do not fit.
    weekend_soups = {**DEFAULT_OPTIONS, "meal_schedule": "weekends", "soup_days": 3.0}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], weekend_soups)
    assert result["errors"] == {"soup_days": "too_many_soup_days"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**DEFAULT_OPTIONS, "soup_days": 3.0, "soup_weekdays": ["mon", "thu"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Obiady"
    assert result["options"]["soup_days"] == 3
    assert result["options"]["soup_weekdays"] == ["mon", "thu"]
    assert "soup_share" not in result["options"]


async def test_options_flow_reloads(hass_pl: HomeAssistant) -> None:
    hass = hass_pl
    entry = make_entry()
    await setup_entry(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**DEFAULT_OPTIONS, "meal_mode": "soup_only"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["meal_mode"] == "soup_only"
    assert entry.state is ConfigEntryState.LOADED


async def test_setup_creates_entities_and_first_plan(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass = hass_pl
    freezer.move_to(local(WEDNESDAY_NOON))
    entry = make_entry()
    await setup_entry(hass, entry)

    assert hass.states.get(entity(hass, entry, "calendar", "plan"))
    assert not hass.states.async_entity_ids("todo")

    # Empty database: nothing could be drawn yet.
    assert hass.states.get(entity(hass, entry, "sensor", "tomorrow")).state == "unknown"

    await fill_database(hass, entry)
    response = await hass.services.async_call(
        DOMAIN, "redraw", {}, blocking=True, return_response=True
    )
    assert response == {"dates": ["2026-11-12", "2026-11-13"]}
    await hass.async_block_till_done()

    tomorrow = hass.states.get(entity(hass, entry, "sensor", "tomorrow"))
    assert tomorrow.state not in ("unknown", "", None)
    assert tomorrow.attributes["date"] == "2026-11-12"
    assert tomorrow.attributes["shopping_items"]

    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": "2026-11-09 00:00:00", "end_date_time": "2026-11-16 00:00:00"},
        target={"entity_id": entity(hass, entry, "calendar", "plan")},
        blocking=True,
        return_response=True,
    )
    plan_events = next(iter(events.values()))["events"]
    # At the default lunch time, 13:00, for the default 30 minutes.
    assert [e["start"] for e in plan_events] == [
        "2026-11-12T13:00:00+01:00", "2026-11-13T13:00:00+01:00"
    ]
    assert [e["end"] for e in plan_events] == [
        "2026-11-12T13:30:00+01:00", "2026-11-13T13:30:00+01:00"
    ]
    for event in plan_events:
        assert event["summary"].startswith("Obiad: ")
        assert event["summary"][7].islower(), event["summary"]
    soup_events = [e for e in plan_events if e["summary"] in ("Obiad: zupa kalafiorowa", "Obiad: zupa grzybowa")]
    planner = entry.runtime_data
    soup_days = [iso for iso, m in planner.plan.items() if m["parts"][0]["category"] == "soup"]
    assert len(soup_events) == len(soup_days)


async def test_soups_follow_the_week_and_the_preferred_days(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """On Wednesday the rest of the week is drawn; its one soup goes to Friday.

    Monday to Wednesday have no lunch in the plan, so they share the soup with
    Thursday and Friday, but Friday is the preferred day and gets it first.
    """
    hass = hass_pl
    freezer.move_to(local(WEDNESDAY_NOON))
    entry = make_entry(soup_days=1, soup_weekdays=["fri"])
    await setup_entry(hass, entry)
    await fill_database(hass, entry)
    for _ in range(5):
        await hass.services.async_call(DOMAIN, "redraw", {}, blocking=True)
        plan = entry.runtime_data.plan
        assert plan["2026-11-13"]["parts"][0]["category"] == "soup"
        assert plan["2026-11-12"]["parts"][0]["category"] != "soup"


async def test_calendar_uses_the_lunch_time(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass = hass_pl
    freezer.move_to(local("2026-11-12 13:10:00"))  # Thursday, during lunch
    entry = make_entry(lunch_time="12:30:00", lunch_duration=60)
    await setup_entry(hass, entry)
    await fill_database(hass, entry)
    planner = entry.runtime_data
    planner.plan["2026-11-12"] = {"date": "2026-11-12", "parts": [
        {"category": "soup", "uid": "x", "name": "Grzybowa", "ingredients": ["Grzybowa"]}
    ]}
    planner._on_midnight(dt_util.now())  # refresh the entities
    await hass.async_block_till_done()

    calendar = hass.states.get(entity(hass, entry, "calendar", "plan"))
    # 12:30-13:30: the lunch is going on now.
    assert calendar.state == "on"
    assert calendar.attributes["message"] == "Obiad: zupa grzybowa"
    assert calendar.attributes["start_time"] == "2026-11-12 12:30:00"

    freezer.move_to(local("2026-11-12 13:40:00"))
    planner._on_midnight(dt_util.now())
    await hass.async_block_till_done()
    calendar = hass.states.get(entity(hass, entry, "calendar", "plan"))
    assert calendar.state == "off"
    assert calendar.attributes["start_time"] != "2026-11-12 12:30:00"


async def test_item_description_and_disabled_items(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass = hass_pl
    freezer.move_to(local(WEDNESDAY_NOON))
    entry = make_entry(meal_mode="soup_only")
    await setup_entry(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        "add_meal",
        {"category": "soup", "name": "Pomidorowa", "ingredients": "passata, śmietana\nmakaron"},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN, "add_meal", {"category": "soup", "name": "Grzybowa", "active": False}, blocking=True
    )
    # November: a soup only in season from May to July is not drawn.
    await hass.services.async_call(
        DOMAIN,
        "add_meal",
        {"category": "soup", "name": "Botwinkowa", "season_from": 5, "season_to": 7},
        blocking=True,
    )
    # Friday's shopping day (Thursday) has not come yet, so Friday can be drawn again.
    planner = entry.runtime_data
    for _ in range(5):
        await hass.services.async_call(DOMAIN, "redraw", {"date": "2026-11-13"}, blocking=True)
        meal = planner.plan["2026-11-13"]
        assert planner.describe(meal) == "Zupa pomidorowa"
        assert meal["parts"][0]["ingredients"] == ["passata", "śmietana", "makaron"]


async def test_add_meal_updates_by_name_and_remove_meal(hass_pl: HomeAssistant) -> None:
    hass = hass_pl
    entry = make_entry()
    await setup_entry(hass, entry)
    planner = entry.runtime_data
    await add_items(hass, entry, "soup", "Pomidorowa")
    await hass.services.async_call(
        DOMAIN, "add_meal", {"category": "soup", "name": "pomidorowa", "ingredients": ["passata"]},
        blocking=True,
    )
    assert [m["ingredients"] for m in planner.items["soup"]] == [["passata"]]

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "add_meal", {"category": "soup", "name": "x", "season_from": 5}, blocking=True
        )
    await hass.services.async_call(
        DOMAIN, "remove_meal", {"category": "soup", "name": "Pomidorowa"}, blocking=True
    )
    assert planner.items["soup"] == []
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "remove_meal", {"category": "soup", "name": "Pomidorowa"}, blocking=True
        )


async def test_websocket_meal_editing(hass_pl: HomeAssistant, hass_ws_client) -> None:
    hass = hass_pl
    entry = make_entry()
    await setup_entry(hass, entry)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "lunch_planner/meals/subscribe", "entry_id": entry.entry_id})
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["event"]["meals"]["soup"] == []

    await client.send_json_auto_id(
        {
            "type": "lunch_planner/meals/save",
            "entry_id": entry.entry_id,
            "category": "soup",
            "name": "  Botwinkowa ",
            "ingredients": ["botwinka", "", "Botwinka", "śmietana"],
            "season": [5, 7],
            "active": True,
        }
    )
    update = await client.receive_json()
    result = await client.receive_json()
    if "event" in result:  # order of the event and the result is not fixed
        update, result = result, update
    assert result["success"]
    uid = result["result"]["uid"]
    meal = update["event"]["meals"]["soup"][0]
    assert meal == {
        "uid": uid, "name": "Botwinkowa", "ingredients": ["botwinka", "śmietana"],
        "season": [5, 7], "active": True,
    }

    # Change it and move it to another category.
    await client.send_json_auto_id(
        {
            "type": "lunch_planner/meals/save", "entry_id": entry.entry_id, "category": "dish",
            "uid": uid, "name": "Botwinkowa", "season": None, "active": False,
        }
    )
    messages = [await client.receive_json(), await client.receive_json()]
    event = next(m for m in messages if "event" in m)["event"]["meals"]
    assert event["soup"] == []
    assert event["dish"][0]["active"] is False and event["dish"][0]["season"] is None

    await client.send_json_auto_id(
        {"type": "lunch_planner/meals/save", "entry_id": entry.entry_id, "category": "soup", "name": " "}
    )
    assert not (await client.receive_json())["success"]

    await client.send_json_auto_id({"type": "lunch_planner/meals/delete", "entry_id": entry.entry_id, "uid": uid})
    messages = [await client.receive_json(), await client.receive_json()]
    assert next(m for m in messages if "event" in m)["event"]["meals"]["dish"] == []

    await client.send_json_auto_id({"type": "lunch_planner/meals/delete", "entry_id": entry.entry_id, "uid": uid})
    assert not (await client.receive_json())["success"]
    await client.send_json_auto_id({"type": "lunch_planner/meals/subscribe", "entry_id": "nope"})
    assert not (await client.receive_json())["success"]


async def test_only_admins_change_the_database_and_draw(
    hass_pl: HomeAssistant,
    hass_ws_client,
    hass_admin_user,
    hass_read_only_user,
    hass_read_only_access_token: str,
) -> None:
    hass = hass_pl
    entry = make_entry()
    await setup_entry(hass, entry)
    await fill_database(hass, entry)
    planner = entry.runtime_data
    button = entity(hass, entry, "button", "redraw")
    user = Context(user_id=hass_read_only_user.id)
    admin = Context(user_id=hass_admin_user.id)
    calls = [
        ("add_meal", {"category": "soup", "name": "Pomidorowa"}),
        ("remove_meal", {"category": "soup", "name": "Grzybowa"}),
        ("redraw", {}),
    ]

    for service, data in calls:
        with pytest.raises(Unauthorized):
            await hass.services.async_call(DOMAIN, service, data, blocking=True, context=user)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "button", "press", {"entity_id": button}, blocking=True, context=user
        )
    assert sorted(m["name"] for m in planner.items["soup"]) == ["Grzybowa", "Kalafiorowa"]

    for service, data in calls:
        await hass.services.async_call(DOMAIN, service, data, blocking=True, context=admin)
    await hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True, context=admin
    )
    assert sorted(m["name"] for m in planner.items["soup"]) == ["Kalafiorowa", "Pomidorowa"]

    # In the panel a user who is not an admin sees the database but cannot change it.
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id({"type": "lunch_planner/meals/subscribe", "entry_id": entry.entry_id})
    assert (await client.receive_json())["success"]
    assert len((await client.receive_json())["event"]["meals"]["soup"]) == 2
    uid = planner.items["soup"][0]["uid"]
    for message in (
        {"type": "lunch_planner/meals/save", "category": "soup", "name": "Ogórkowa"},
        {"type": "lunch_planner/meals/delete", "uid": uid},
    ):
        await client.send_json_auto_id({**message, "entry_id": entry.entry_id})
        response = await client.receive_json()
        assert not response["success"]
        assert response["error"]["code"] == "unauthorized"
    assert len(planner.items["soup"]) == 2


async def test_migration_from_todo_lists(hass_pl: HomeAssistant, hass_storage) -> None:
    """Version 0.2 kept meals as to-do items; they become meals, the lists go away."""
    hass = hass_pl
    entry = make_entry()
    entry.add_to_hass(hass)
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {
            "items": {
                "soup": [
                    {"uid": "a", "summary": "Botwinkowa", "description": "botwinka\nsezon: 5-7", "done": False},
                    {"uid": "b", "summary": "Kalafiorowa", "description": "zupa kalafiorowa (mrożonka)", "done": True},
                ],
                "dish": [{"uid": "c", "summary": "Spaghetti", "description": "", "done": False}],
            },
            "plan": {},
        },
    }
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "todo", DOMAIN, f"{entry.entry_id}_soup", config_entry=entry, suggested_object_id="obiady_zupy"
    )
    await setup_entry(hass, entry)

    soups = entry.runtime_data.items["soup"]
    assert soups == [
        {"uid": "a", "name": "Botwinkowa", "ingredients": ["botwinka"], "season": [5, 7], "active": True},
        {"uid": "b", "name": "Kalafiorowa", "ingredients": ["zupa kalafiorowa (mrożonka)"], "season": None, "active": False},
    ]
    assert entry.runtime_data.items["dish"][0]["ingredients"] == []
    assert registry.async_get(old.entity_id) is None


def capture_plan_events(hass: HomeAssistant) -> list:
    events = []
    hass.bus.async_listen(f"{DOMAIN}_plan_updated", events.append)
    return events


async def test_weekly_draw_event_lists_the_whole_week(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Monday is drawn at midnight (its shopping day, Saturday, has come);
    the Saturday 09:00 draw adds Tue-Fri and its event lists all five days."""
    hass = hass_pl
    freezer.move_to(local("2026-11-13 18:00:00"))  # Friday
    entry = make_entry()
    await setup_entry(hass, entry)
    await fill_database(hass, entry)
    planner = entry.runtime_data
    planner.plan.clear()
    events = capture_plan_events(hass)

    freezer.move_to(local("2026-11-14 00:00:05"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert [e.data["reason"] for e in events] == ["missing"]
    assert events[0].data["drawn"] == ["2026-11-16"]
    monday = planner.plan["2026-11-16"]

    freezer.move_to(local("2026-11-14 09:00:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    weekly = events[-1].data
    assert weekly["reason"] == "weekly"
    assert weekly["entry_id"] == entry.entry_id
    assert weekly["drawn"] == ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
    assert [m["date"] for m in weekly["meals"]] == [
        "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"
    ]
    assert weekly["summary"].splitlines()[0].startswith("pon 16.11: ")
    assert planner.plan["2026-11-16"] == monday


async def test_start_waits_for_the_weekly_draw(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A start on Friday evening leaves the next week to Saturday's draw;
    a start on Sunday, after a missed draw, plans the next week at once."""
    hass = hass_pl
    freezer.move_to(local("2026-11-13 18:00:00"))  # Friday
    entry = make_entry()
    await setup_entry(hass, entry)
    await fill_database(hass, entry)
    planner = entry.runtime_data
    planner.plan.clear()
    events = capture_plan_events(hass)

    planner.async_ensure_plan()
    await hass.async_block_till_done()
    assert planner.plan == {}
    assert events == []

    freezer.move_to(local("2026-11-15 10:00:00"))  # Sunday; Saturday's draw was missed
    planner.async_ensure_plan()
    await hass.async_block_till_done()
    assert sorted(planner.plan) == [
        "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"
    ]
    assert [e.data["reason"] for e in events] == ["first"]


async def test_shopping_day_lock_and_to_buy_sensor(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass = hass_pl
    freezer.move_to(local("2026-11-13 18:00:00"))  # Friday
    entry = make_entry()
    await setup_entry(hass, entry)
    await hass.services.async_call(
        DOMAIN, "add_meal",
        {"category": "soup", "name": "Pomidorowa", "ingredients": ["passata", "makaron"]},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN, "add_meal", {"category": "soup", "name": "Grzybowa"}, blocking=True
    )
    planner = entry.runtime_data
    await hass.services.async_call(DOMAIN, "redraw", {}, blocking=True)
    assert "2026-11-16" in planner.plan

    # Friday: Monday can still change.
    assert not planner.is_locked(dt_util.parse_date("2026-11-16"))

    # Saturday is Monday's shopping day (shops are closed on Sunday): locked.
    freezer.move_to(local("2026-11-14 08:00:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    monday = planner.plan["2026-11-16"]
    await hass.services.async_call(DOMAIN, "redraw", {}, blocking=True)
    assert planner.plan["2026-11-16"] == monday
    with pytest.raises(Exception):
        await hass.services.async_call(DOMAIN, "redraw", {"date": "2026-11-16"}, blocking=True)

    to_buy = entity(hass, entry, "sensor", "to_buy")
    planner._on_midnight(dt_util.now())  # refresh the entities
    await hass.async_block_till_done()
    state = hass.states.get(to_buy)
    assert state.attributes["shopping_date"] == "2026-11-14"
    assert state.attributes["meal_dates"] == ["2026-11-16"]
    expected = monday["parts"][0]["ingredients"]
    assert state.attributes["shopping_items"] == expected
    assert state.state == ", ".join(expected)
    assert state.attributes["summary"].startswith("pon 16.11: Zupa ")

    # Sunday: nothing to buy today, the next list is Monday's (for Tuesday).
    freezer.move_to(local("2026-11-15 10:00:00"))
    planner._on_midnight(dt_util.now())
    await hass.async_block_till_done()
    assert hass.states.get(to_buy).attributes["shopping_date"] == "2026-11-16"


async def test_options_migration_and_old_button_removed(hass_pl: HomeAssistant) -> None:
    """0.3 entries had notification options and a "send shopping list" button."""
    hass = hass_pl
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Obiady",
        version=1,
        minor_version=1,
        options={
            **{k: v for k, v in DEFAULT_OPTIONS.items() if k not in ("meal_schedule", "workdays")},
            "meal_days": ["mon", "tue", "wed", "thu", "fri"],
            "shopping_mode": "time",
            "shopping_time": "17:00:00",
            "notify_services": ["notify.mobile_app_phone"],
            "shopping_list": "todo.shopping_list",
            "person": "person.x",
            "arrival_delay": 15,
        },
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "button", DOMAIN, f"{entry.entry_id}_send_shopping", config_entry=entry
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.minor_version == 3
    assert dict(entry.options) == DEFAULT_OPTIONS
    assert registry.async_get(old.entity_id) is None
    assert hass.states.get(entity(hass, entry, "button", "redraw"))


async def test_panel_and_hidden_lists(hass_pl: HomeAssistant, hass_client) -> None:
    hass = hass_pl
    entry = make_entry()
    await setup_entry(hass, entry)

    panels = hass.data["frontend_panels"]
    assert "lunch-planner" in panels
    panel = panels["lunch-planner"]
    assert panel.sidebar_title == "Obiady"
    planner_config = panel.config["planners"][0]
    assert planner_config["entities"]["plan"] == entity(hass, entry, "calendar", "plan")
    assert planner_config["entry_id"] == entry.entry_id
    assert planner_config["entities"]["redraw"] == entity(hass, entry, "button", "redraw")
    assert planner_config["entities"]["to_buy"] == entity(hass, entry, "sensor", "to_buy")
    assert "send_shopping" not in planner_config["entities"]
    assert panel.config["_panel_custom"]["module_url"].startswith("/lunch_planner_static/panel.js?v=")

    client = await hass_client()
    response = await client.get("/lunch_planner_static/panel.js")
    assert response.status == 200
    assert "lunch-planner-panel" in await response.text()

    # Turning the panel off removes it; unloading removes it as well.
    hass.config_entries.async_update_entry(entry, options={**entry.options, "show_panel": False})
    await hass.async_block_till_done()
    assert "lunch-planner" not in hass.data["frontend_panels"]
    hass.config_entries.async_update_entry(entry, options={**entry.options, "show_panel": True})
    await hass.async_block_till_done()
    assert "lunch-planner" in hass.data["frontend_panels"]
    await hass.config_entries.async_unload(entry.entry_id)
    assert "lunch-planner" not in hass.data["frontend_panels"]


async def test_unload_and_remove(hass_pl: HomeAssistant) -> None:
    hass = hass_pl
    entry = make_entry()
    await setup_entry(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    await hass.config_entries.async_remove(entry.entry_id)


async def test_meal_days_become_work_days(hass_pl: HomeAssistant) -> None:
    """0.5 had a list of meal days; it becomes the work days, lunches on work days."""
    hass = hass_pl
    old = {k: v for k, v in DEFAULT_OPTIONS.items() if k not in ("meal_schedule", "workdays")}
    entry = MockConfigEntry(
        domain=DOMAIN, title="Obiady", version=1, minor_version=2,
        options={**old, "meal_days": ["mon", "wed", "fri"]},
    )
    await setup_entry(hass, entry)
    assert entry.minor_version == 3
    assert entry.options["workdays"] == ["mon", "wed", "fri"]
    assert entry.options["meal_schedule"] == "workdays"
    assert "meal_days" not in entry.options
    assert entry.runtime_data.meal_weekdays == [0, 2, 4]


@pytest.mark.parametrize(
    ("schedule", "weekdays"),
    [("workdays", [0, 1, 2, 3, 4]), ("weekends", [5, 6]), ("every_day", [0, 1, 2, 3, 4, 5, 6])],
)
async def test_meal_schedule(hass_pl: HomeAssistant, schedule: str, weekdays: list[int]) -> None:
    hass = hass_pl
    entry = make_entry(meal_schedule=schedule)
    await setup_entry(hass, entry)
    assert entry.runtime_data.meal_weekdays == weekdays


class FakeCalendar(CalendarEntity):
    """A calendar whose all-day events are set by the test."""

    def __init__(self, name: str, days: list[str]) -> None:
        self._attr_name = name
        self._attr_unique_id = name
        self.days = days

    @property
    def event(self) -> CalendarEvent | None:
        return None

    async def async_get_events(self, hass, start_date, end_date) -> list[CalendarEvent]:
        events = [
            CalendarEvent(
                start=date.fromisoformat(d),
                end=date.fromisoformat(d) + timedelta(days=1),
                summary=self.name,
            )
            for d in self.days
        ]
        # A meeting with a time of day is not a day off.
        events.append(
            CalendarEvent(
                start=local("2026-12-21 10:00:00"),
                end=local("2026-12-21 11:00:00"),
                summary="Meeting",
            )
        )
        return events


async def setup_calendars(hass: HomeAssistant) -> tuple[FakeCalendar, FakeCalendar]:
    """A public holidays calendar (Holiday integration) and a holiday trip calendar."""
    holidays = FakeCalendar("Holidays", ["2026-12-24", "2026-12-25", "2026-12-26"])
    trips = FakeCalendar("Trips", ["2026-12-22"])
    for platform, calendar in (("holiday", holidays), ("trips", trips)):
        mock_integration(hass, MockModule(platform))

        async def setup_platform(hass, config, add_entities, discovery_info=None, calendar=calendar):
            add_entities([calendar])

        mock_platform(hass, f"{platform}.calendar", MockPlatform(async_setup_platform=setup_platform))
    assert await async_setup_component(
        hass, "calendar", {"calendar": [{"platform": "holiday"}, {"platform": "trips"}]}
    )
    await hass.async_block_till_done()
    return holidays, trips


async def test_days_off_and_morning_shopping(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass = hass_pl
    freezer.move_to(local("2026-12-21 10:00:00"))  # Monday before Christmas
    _, trips = await setup_calendars(hass)
    entry = make_entry(days_off_calendars=["calendar.holidays", "calendar.trips"])
    await setup_entry(hass, entry)
    await fill_database(hass, entry)
    planner = entry.runtime_data

    # Tuesday is a trip, Thursday and Friday are holidays: only Wednesday.
    response = await hass.services.async_call(
        DOMAIN, "redraw", {}, blocking=True, return_response=True
    )
    assert response == {"dates": ["2026-12-23"]}
    # The trip closes no shops; the holidays do.
    assert date(2026, 12, 22) not in planner.shops_closed
    assert date(2026, 12, 24) in planner.shops_closed
    assert planner.shopping_day(date(2026, 12, 23)) == date(2026, 12, 22)

    # Monday 28.12: 24-27.12 closed, so it is bought that morning; the list
    # goes out on Sunday evening.
    await hass.services.async_call(DOMAIN, "redraw", {"date": "2026-12-28"}, blocking=True)
    assert planner.shopping_day(date(2026, 12, 28)) == date(2026, 12, 28)
    with pytest.raises(Exception):
        await hass.services.async_call(DOMAIN, "redraw", {"date": "2026-12-24"}, blocking=True)

    # A trip added after the draw removes Wednesday's lunch at midnight.
    trips.days = ["2026-12-22", "2026-12-23"]
    planner._on_midnight(dt_util.now())
    await hass.async_block_till_done()
    assert "2026-12-23" not in planner.plan
    assert "2026-12-28" in planner.plan

    freezer.move_to(local("2026-12-27 18:00:00"))
    planner._on_midnight(dt_util.now())
    await hass.async_block_till_done()
    state = hass.states.get(entity(hass, entry, "sensor", "to_buy"))
    assert state.attributes["shopping_date"] == "2026-12-28"
    assert state.attributes["shopping_morning"] is True
    assert state.attributes["list_date"] == "2026-12-27"
    assert state.attributes["meal_dates"] == ["2026-12-28"]
    assert planner.is_locked(date(2026, 12, 28))

    # The list is out: a trip added now keeps the lunch.
    trips.days = ["2026-12-28"]
    planner._on_midnight(dt_util.now())
    await hass.async_block_till_done()
    assert "2026-12-28" in planner.plan


async def test_holiday_shops_open_when_switched_off(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass = hass_pl
    freezer.move_to(local("2026-12-21 10:00:00"))
    await setup_calendars(hass)
    entry = make_entry(days_off_calendars=["calendar.holidays"], holiday_shops_closed=False)
    await setup_entry(hass, entry)
    planner = entry.runtime_data
    assert planner.days_off == {date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 26)}
    assert planner.shops_closed == set()
    # Saturday 26.12 is open now, two days before Monday.
    assert planner.shopping_day(date(2026, 12, 28)) == date(2026, 12, 26)


async def test_days_off_far_ahead(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Drawing one day weeks ahead reads the days-off calendars that far."""
    hass = hass_pl
    freezer.move_to(local("2026-11-11 12:00:00"))
    await setup_calendars(hass)
    entry = make_entry(days_off_calendars=["calendar.holidays"])
    await setup_entry(hass, entry)
    await fill_database(hass, entry)
    with pytest.raises(Exception):
        await hass.services.async_call(DOMAIN, "redraw", {"date": "2026-12-24"}, blocking=True)
    await hass.services.async_call(DOMAIN, "redraw", {"date": "2026-12-23"}, blocking=True)
    assert "2026-12-23" in entry.runtime_data.plan


def test_default_week_start_by_country() -> None:
    assert default_week_start("PL") == "mon"
    assert default_week_start("us") == "sun"
    assert default_week_start("AE") == "sat"
    assert default_week_start(None) == "mon"


async def test_week_start_defaults_to_the_country(hass_pl: HomeAssistant) -> None:
    """Without the option (e.g. a planner from 0.6.0) the country decides."""
    hass = hass_pl
    hass.config.country = "US"
    entry = make_entry()
    assert "week_start" not in entry.options
    await setup_entry(hass, entry)
    assert entry.runtime_data.week_start == 6
    result = await hass.config_entries.options.async_init(entry.entry_id)
    defaults = {str(k): k.default() for k in result["data_schema"].schema if callable(getattr(k, "default", None))}
    assert defaults["week_start"] == "sun"


async def test_weekly_draw_with_week_from_sunday(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Lunches every day, weeks from Sunday: the Saturday draw plans Sun-Sat."""
    hass = hass_pl
    freezer.move_to(local("2026-11-13 18:00:00"))  # Friday
    entry = make_entry(meal_schedule="every_day", week_start="sun", no_shopping_days=[])
    await setup_entry(hass, entry)
    await fill_database(hass, entry)
    planner = entry.runtime_data
    planner.plan.clear()
    events = capture_plan_events(hass)

    # Sunday's lunch is bought on Saturday: drawn at Saturday midnight.
    freezer.move_to(local("2026-11-14 00:00:05"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert events[-1].data["drawn"] == ["2026-11-15"]

    freezer.move_to(local("2026-11-14 09:00:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    weekly = events[-1].data
    assert weekly["reason"] == "weekly"
    assert weekly["drawn"] == [f"2026-11-{d}" for d in range(16, 22)]
    assert [m["date"] for m in weekly["meals"]] == [f"2026-11-{d}" for d in range(15, 22)]
