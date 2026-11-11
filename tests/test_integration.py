"""Tests of Lunch Planner running inside Home Assistant."""

from __future__ import annotations

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
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


@pytest.fixture
def notify_calls(hass: HomeAssistant):
    return async_mock_service(hass, "notify", "mobile_app_phone")


def make_entry(**options) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Obiady",
        options={**DEFAULT_OPTIONS, "notify_services": ["notify.mobile_app_phone"], **options},
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
    assert [e["start"] for e in plan_events] == ["2026-11-12", "2026-11-13"]
    for event in plan_events:
        assert event["summary"].startswith("Obiad: ")
        assert event["summary"][7].islower(), event["summary"]
    soup_events = [e for e in plan_events if e["summary"] in ("Obiad: zupa kalafiorowa", "Obiad: zupa grzybowa")]
    planner = entry.runtime_data
    soup_days = [iso for iso, m in planner.plan.items() if m["parts"][0]["category"] == "soup"]
    assert len(soup_events) == len(soup_days)


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
    for _ in range(5):
        await hass.services.async_call(DOMAIN, "redraw", {"date": "2026-11-12"}, blocking=True)
        await hass.async_block_till_done()
        state = hass.states.get(entity(hass, entry, "sensor", "tomorrow"))
        assert state.state == "Zupa pomidorowa"
        assert state.attributes["shopping_items"] == ["passata", "śmietana", "makaron"]


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


async def test_weekly_draw_and_redraw_button_in_notification(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory, notify_calls
) -> None:
    hass = hass_pl
    freezer.move_to(local("2026-11-14 08:59:00"))  # Saturday
    entry = make_entry()
    await setup_entry(hass, entry)
    await fill_database(hass, entry)

    freezer.move_to(local("2026-11-14 09:00:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert len(notify_calls) == 1
    message = notify_calls[0].data["message"].splitlines()
    assert [line.split(":")[0] for line in message] == [
        "pon 16.11", "wt 17.11", "śr 18.11", "czw 19.11", "pt 20.11"
    ]
    action = notify_calls[0].data["data"]["actions"][0]["action"]
    assert action == f"LUNCH_PLANNER_REDRAW_{entry.entry_id}"

    hass.bus.async_fire("mobile_app_notification_action", {"action": action})
    await hass.async_block_till_done()
    assert len(notify_calls) == 2


async def test_saturday_shopping_for_monday_and_lock(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory, notify_calls
) -> None:
    hass = hass_pl
    freezer.move_to(local("2026-11-13 18:00:00"))  # Friday, after shopping time
    entry = make_entry(shopping_list="todo.shopping_list")
    await setup_entry(hass, MockConfigEntry(domain="shopping_list"))
    assert hass.states.get("todo.shopping_list")
    await setup_entry(hass, entry)
    await fill_database(hass, entry)

    # Saturday 17:00: the weekly draw has not happened on purpose (it is set to
    # Sunday), so Monday's lunch is drawn on the spot and bought now.
    await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(entry, options={**entry.options, "draw_weekday": "sun"})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    freezer.move_to(local("2026-11-14 17:00:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    planner = entry.runtime_data
    shopping = [c for c in notify_calls if "pon 16.11" in c.data["title"]]
    assert len(shopping) == 1, (
        sorted(planner.plan), [c.data.get("title") for c in notify_calls], planner.today()
    )
    monday = planner.plan["2026-11-16"]

    items = await hass.services.async_call(
        "todo", "get_items", {}, target={"entity_id": "todo.shopping_list"},
        blocking=True, return_response=True,
    )
    on_list = [i["summary"] for i in items["todo.shopping_list"]["items"]]
    # The shopping list file outlives a test run, so only check our items are on it.
    assert {i for p in monday["parts"] for i in p["ingredients"]} <= set(on_list)

    # Monday is bought for, so drawing again leaves it alone.
    await hass.services.async_call(DOMAIN, "redraw", {}, blocking=True)
    assert planner.plan["2026-11-16"] == monday

    # Sunday: shops closed, nothing to send.
    freezer.move_to(local("2026-11-15 17:00:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len([c for c in notify_calls if c.data["title"].startswith("Zakupy")]) == 1


async def test_presence_mode_waits_until_home(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory, notify_calls
) -> None:
    hass = hass_pl
    hass.states.async_set("person.marzena", "not_home")
    freezer.move_to(local("2026-11-16 10:00:00"))  # Monday
    entry = make_entry(shopping_mode="presence", person="person.marzena")
    await setup_entry(hass, entry)
    await fill_database(hass, entry)
    await hass.services.async_call(DOMAIN, "redraw", {}, blocking=True)

    freezer.move_to(local("2026-11-16 17:00:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not [c for c in notify_calls if c.data["title"].startswith("Zakupy")]

    freezer.move_to(local("2026-11-16 18:30:00"))
    hass.states.async_set("person.marzena", "home")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=14))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not [c for c in notify_calls if c.data["title"].startswith("Zakupy")]

    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    sent = [c for c in notify_calls if c.data["title"].startswith("Zakupy")]
    assert len(sent) == 1
    assert "wt 17.11" in sent[0].data["title"]


async def test_presence_mode_late_arrival_is_skipped(
    hass_pl: HomeAssistant, freezer: FrozenDateTimeFactory, notify_calls
) -> None:
    hass = hass_pl
    hass.states.async_set("person.marzena", "not_home")
    freezer.move_to(local("2026-11-16 10:00:00"))
    entry = make_entry(shopping_mode="presence", person="person.marzena", arrival_delay=0)
    await setup_entry(hass, entry)
    await fill_database(hass, entry)
    await hass.services.async_call(DOMAIN, "redraw", {}, blocking=True)

    freezer.move_to(local("2026-11-16 17:00:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    freezer.move_to(local("2026-11-16 22:30:00"))
    hass.states.async_set("person.marzena", "home")
    await hass.async_block_till_done()
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not [c for c in notify_calls if c.data["title"].startswith("Zakupy")]


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
