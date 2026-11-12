"""The bundled blueprints load, and automations made from them are valid."""

from __future__ import annotations

from pathlib import Path
import shutil
from unittest.mock import patch

import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components import automation
from homeassistant.components.blueprint import models
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml

SOURCE = Path(__file__).parents[1] / "blueprints" / "automation" / "lunch_planner"
BLUEPRINTS = sorted(p.name for p in SOURCE.glob("*.yaml"))

# The phone notification is a mobile_app device action. Loading the real one
# imports mobile_app, which pulls in a dozen integrations with native
# requirements (camera, cloud, voice), so these tests check the device action
# against the fields mobile_app accepts instead.
_MOBILE_APP_NOTIFY = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required("type"): "notify",
        vol.Required("message"): cv.template,
        vol.Optional("title"): cv.template,
        vol.Optional("data"): cv.template_complex,
    }
)


async def _validate_device_action(hass, config):
    return _MOBILE_APP_NOTIFY(config)


@pytest.mark.parametrize("name", BLUEPRINTS)
def test_blueprint_schema(name):
    blueprint = models.Blueprint(
        load_yaml(SOURCE / name), expected_domain="automation", schema=BLUEPRINT_SCHEMA
    )
    meta = blueprint.metadata
    assert meta["source_url"].endswith(f"blueprints/automation/lunch_planner/{name}")
    assert meta["homeassistant"]["min_version"]


@pytest.fixture
async def phone(hass: HomeAssistant) -> str:
    entry = MockConfigEntry(domain="mobile_app", data={"webhook_id": "abc"})
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mobile_app", "phone")}, name="Phone"
    )
    return device.id


async def test_automations_from_blueprints_load(
    hass: HomeAssistant, phone: str, caplog: pytest.LogCaptureFixture
) -> None:
    target = Path(hass.config.path("blueprints", "automation", "lunch_planner"))
    target.mkdir(parents=True, exist_ok=True)
    for name in BLUEPRINTS:
        shutil.copy(SOURCE / name, target / name)
    try:
        with patch(
            "homeassistant.components.device_automation.action.async_validate_action_config",
            _validate_device_action,
        ):
            assert await async_setup_component(
                hass,
                automation.DOMAIN,
                {
                    automation.DOMAIN: [
                        {
                            "id": "shopping",
                            "alias": "Shopping",
                            "use_blueprint": {
                                "path": "lunch_planner/shopping_list.yaml",
                                "input": {
                                    "to_buy_sensor": "sensor.obiady_do_kupienia",
                                    "notify_device": phone,
                                    "shopping_lists": ["todo.shopping_list"],
                                    "person": "person.marzena",
                                    "work_zone": "zone.work",
                                },
                            },
                        },
                        {
                            "id": "plan",
                            "alias": "Plan",
                            "use_blueprint": {
                                "path": "lunch_planner/weekly_plan.yaml",
                                "input": {
                                    "redraw_button": "button.obiady_losuj",
                                    "notify_device": phone,
                                },
                            },
                        },
                    ]
                },
            )
            await hass.async_block_till_done()
        for entity_id in ("automation.shopping", "automation.plan"):
            state = hass.states.get(entity_id)
            errors = [
                f"{r.levelname}: {r.getMessage()}" for r in caplog.records if r.levelno >= 30
            ]
            assert state is not None and state.state == "on", (entity_id, state, errors)
        await hass.services.async_call(
            automation.DOMAIN, "turn_off", {"entity_id": "all"}, blocking=True
        )
    finally:
        shutil.rmtree(target)
