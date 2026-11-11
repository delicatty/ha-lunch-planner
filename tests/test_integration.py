"""Tests of Lunch Planner running inside Home Assistant."""

from __future__ import annotations

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.lunch_planner.const import DEFAULT_OPTIONS, DOMAIN

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
        minor_version=2,
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

    bad = {**DEFAULT_OPTIONS, "meal_days": []}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], bad)
    assert result["errors"] == {"meal_days": "no_meal_days"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**DEFAULT_OPTIONS, "soup_share": 40.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Obiady"
    assert result["options"]["soup_share"] == 40


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
            **DEFAULT_OPTIONS,
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
    assert entry.minor_version == 2
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
