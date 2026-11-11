"""Config and options flow for Lunch Planner."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_AVOID_PREVIOUS_WEEK,
    CONF_DRAW_TIME,
    CONF_DRAW_WEEKDAY,
    CONF_MEAL_DAYS,
    CONF_MEAL_MODE,
    CONF_NO_SHOPPING_DAYS,
    CONF_SHOW_PANEL,
    CONF_SOUP_SHARE,
    DEFAULT_OPTIONS,
    DOMAIN,
    MEAL_MODES,
    WEEKDAYS,
)
from .texts import async_load_texts

def _weekday_selector(multiple: bool) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(WEEKDAYS),
            multiple=multiple,
            translation_key="weekday",
            mode=selector.SelectSelectorMode.LIST if multiple else selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _options_schema(hass: HomeAssistant, current: dict[str, Any]) -> vol.Schema:
    def default(key: str) -> dict[str, Any]:
        value = current.get(key, DEFAULT_OPTIONS.get(key))
        return {} if value is None else {"default": value}

    return vol.Schema(
        {
            vol.Required(CONF_MEAL_DAYS, **default(CONF_MEAL_DAYS)): _weekday_selector(True),
            vol.Required(CONF_MEAL_MODE, **default(CONF_MEAL_MODE)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(MEAL_MODES),
                    translation_key="meal_mode",
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Required(CONF_SOUP_SHARE, **default(CONF_SOUP_SHARE)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=10, unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_AVOID_PREVIOUS_WEEK, **default(CONF_AVOID_PREVIOUS_WEEK)
            ): selector.BooleanSelector(),
            vol.Required(CONF_DRAW_WEEKDAY, **default(CONF_DRAW_WEEKDAY)): _weekday_selector(False),
            vol.Required(CONF_DRAW_TIME, **default(CONF_DRAW_TIME)): selector.TimeSelector(),
            vol.Required(
                CONF_NO_SHOPPING_DAYS, **default(CONF_NO_SHOPPING_DAYS)
            ): _weekday_selector(True),
            vol.Required(CONF_SHOW_PANEL, **default(CONF_SHOW_PANEL)): selector.BooleanSelector(),
        }
    )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_SOUP_SHARE] = int(data[CONF_SOUP_SHARE])
    return data


class LunchPlannerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a planner: a name first, then the same settings as in Configure."""

    VERSION = 1
    # 1.2: the notification options moved out to automations (blueprints).
    MINOR_VERSION = 2

    def __init__(self) -> None:
        self._name: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._name = user_input[CONF_NAME]
            return await self.async_step_settings()
        default_name = (await async_load_texts(self.hass)).get("default_name", "Lunch planner")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME, default=default_name): str}),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = _validate(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_create_entry(title=self._name, data={}, options=_clean(user_input))
        return self.async_show_form(
            step_id="settings",
            data_schema=_options_schema(self.hass, user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return LunchPlannerOptionsFlow()


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not user_input.get(CONF_MEAL_DAYS):
        errors[CONF_MEAL_DAYS] = "no_meal_days"
    if len(user_input.get(CONF_NO_SHOPPING_DAYS, [])) >= 7:
        errors[CONF_NO_SHOPPING_DAYS] = "no_shopping_day_left"
    return errors


class LunchPlannerOptionsFlow(OptionsFlow):
    """Change the settings of a planner."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = _validate(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_create_entry(data=_clean(user_input))
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.hass, user_input or dict(self.config_entry.options)),
            errors=errors,
        )
