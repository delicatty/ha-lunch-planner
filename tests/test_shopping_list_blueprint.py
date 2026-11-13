"""When the shopping list blueprint sends the list."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
import shutil
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.components import automation
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from test_blueprints import SOURCE, _validate_device_action

SENSOR = "sensor.to_buy"
PERSON = "person.anna"
WORK = "zone.work"
TODAY = "2026-11-12"


def _at(hour: int, minute: int = 0, day: str = TODAY) -> datetime:
    return dt_util.as_utc(
        datetime.fromisoformat(f"{day}T{hour:02}:{minute:02}:00").replace(
            tzinfo=dt_util.get_default_time_zone()
        )
    )


class Shopping:
    """The automation under test, its clock and the notifications it sent."""

    def __init__(self, hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
        self.hass = hass
        self.freezer = freezer
        self.sent: list[str] = []

    async def record(self, hass, config, variables, context) -> None:
        self.sent.append(config["message"].async_render(variables))

    async def setup(self, **leaving_work: Any) -> None:
        assert await async_setup_component(
            self.hass,
            automation.DOMAIN,
            {
                automation.DOMAIN: {
                    "id": "shopping",
                    "alias": "Shopping",
                    "use_blueprint": {
                        "path": "lunch_planner/shopping_list.yaml",
                        "input": {
                            "to_buy_sensor": SENSOR,
                            "notify_device": "phone",
                            **leaving_work,
                        },
                    },
                }
            },
        )
        await self.hass.async_block_till_done()
        assert self.hass.states.get("automation.shopping").state == "on"

    async def time(self, hour: int, minute: int = 0) -> None:
        moment = _at(hour, minute)
        self.freezer.move_to(moment)
        async_fire_time_changed(self.hass, moment)
        await self.hass.async_block_till_done()

    async def at_work(self, at_work: bool) -> None:
        self.hass.states.async_set(PERSON, "Work" if at_work else "not_home")
        self.hass.states.async_set(
            WORK, "1" if at_work else "0", {"persons": [PERSON] if at_work else []}
        )
        await self.hass.async_block_till_done()


@pytest.fixture
async def shopping(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> AsyncIterator[Shopping]:
    await hass.config.async_set_time_zone("Europe/Warsaw")
    freezer.move_to(_at(8))
    hass.states.async_set(
        SENSOR,
        "bread",
        {
            "list_date": TODAY,
            "shopping_items": ["bread"],
            "summary": "Fri: Soup",
            "meal_dates": ["2026-11-13"],
        },
    )
    target = Path(hass.config.path("blueprints", "automation", "lunch_planner"))
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(SOURCE / "shopping_list.yaml", target / "shopping_list.yaml")
    shopping = Shopping(hass, freezer)
    with (
        patch(
            "homeassistant.components.device_automation.action.async_validate_action_config",
            _validate_device_action,
        ),
        patch(
            "homeassistant.components.device_automation.action.async_call_action_from_config",
            shopping.record,
        ),
    ):
        yield shopping
        # Stop the time triggers, or their timers outlive the test.
        await hass.services.async_call(
            automation.DOMAIN, "turn_off", {"entity_id": "all"}, blocking=True
        )
    shutil.rmtree(target)


WORK_INPUTS = {"person": PERSON, "work_zone": WORK}


async def test_without_work_zone_sends_at_the_set_time(shopping: Shopping) -> None:
    await shopping.setup()
    await shopping.time(16, 59)
    assert shopping.sent == []
    await shopping.time(17)
    assert len(shopping.sent) == 1
    assert "bread" in shopping.sent[0] and "Fri: Soup" in shopping.sent[0]
    await shopping.time(20)
    assert len(shopping.sent) == 1


async def test_not_at_work_sends_at_the_set_time(shopping: Shopping) -> None:
    await shopping.at_work(False)
    await shopping.setup(**WORK_INPUTS)
    await shopping.time(17)
    assert len(shopping.sent) == 1
    await shopping.time(20)
    assert len(shopping.sent) == 1


async def test_at_work_sends_when_leaving(shopping: Shopping) -> None:
    await shopping.at_work(True)
    await shopping.setup(**WORK_INPUTS)
    await shopping.time(17)
    assert shopping.sent == []
    await shopping.time(17, 40)
    await shopping.at_work(False)
    assert len(shopping.sent) == 1
    # Back at work and out again: still one list a day.
    await shopping.at_work(True)
    await shopping.time(18)
    await shopping.at_work(False)
    await shopping.time(20)
    assert len(shopping.sent) == 1


async def test_leaving_after_earliest_time_sends_before_the_set_time(
    shopping: Shopping,
) -> None:
    await shopping.at_work(True)
    await shopping.setup(**WORK_INPUTS)
    await shopping.time(16)
    await shopping.at_work(False)
    assert len(shopping.sent) == 1
    await shopping.time(17)
    assert len(shopping.sent) == 1


async def test_lunch_break_does_not_send_and_latest_time_does(shopping: Shopping) -> None:
    await shopping.at_work(True)
    await shopping.setup(**WORK_INPUTS)
    await shopping.time(12)
    await shopping.at_work(False)
    await shopping.time(13)
    await shopping.at_work(True)
    await shopping.time(17)
    assert shopping.sent == []
    await shopping.time(20)
    assert len(shopping.sent) == 1


async def test_nothing_on_other_days(hass: HomeAssistant, shopping: Shopping) -> None:
    hass.states.async_set(
        SENSOR, "bread", {"list_date": "2026-11-14", "shopping_items": ["bread"]}
    )
    await shopping.at_work(True)
    await shopping.setup(**WORK_INPUTS)
    await shopping.time(16)
    await shopping.at_work(False)
    await shopping.time(17)
    await shopping.time(20)
    assert shopping.sent == []


async def change_lunch(hass: HomeAssistant, day: str, items: list[str]) -> None:
    """The planner changed a lunch: new things to buy, then the event."""
    hass.states.async_set(
        SENSOR,
        items[0],
        {"list_date": TODAY, "shopping_items": items, "summary": "Fri: Chop",
         "meal_dates": ["2026-11-13"]},
    )
    hass.bus.async_fire(
        "lunch_planner_plan_updated", {"entry_id": "x", "reason": "swap", "drawn": [day]}
    )
    await hass.async_block_till_done()


async def test_a_change_after_the_list_went_out_sends_it_again(
    hass: HomeAssistant, shopping: Shopping
) -> None:
    await shopping.setup()
    # Before the list went out: nothing extra, the list then has the change.
    await shopping.time(16)
    await change_lunch(hass, "2026-11-13", ["rice"])
    assert shopping.sent == []
    await shopping.time(17)
    assert len(shopping.sent) == 1 and "rice" in shopping.sent[0]

    # A change of another day's lunch is not on today's list.
    await shopping.time(17, 30)
    await change_lunch(hass, "2026-11-17", ["rice"])
    assert len(shopping.sent) == 1

    await change_lunch(hass, "2026-11-13", ["potatoes"])
    assert len(shopping.sent) == 2 and "potatoes" in shopping.sent[1]
