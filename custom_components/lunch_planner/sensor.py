"""Sensors: today's and tomorrow's lunch, and the next shopping trip."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LunchPlannerConfigEntry
from .entity import LunchPlannerEntity
from .manager import LunchPlanner
from .planner import meal_shopping_items, meal_title


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LunchPlannerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    planner = entry.runtime_data
    async_add_entities(
        [
            MealSensor(planner, "today", 0),
            MealSensor(planner, "tomorrow", 1),
            ShoppingSensor(planner, "next_shopping"),
        ]
    )


def _meal_attributes(meal: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": meal["date"],
        "parts": [{"category": p["category"], "name": p["name"]} for p in meal["parts"]],
        "shopping_items": meal_shopping_items([meal]),
    }


class MealSensor(LunchPlannerEntity, SensorEntity):
    """The lunch planned for a day relative to today."""

    def __init__(self, planner: LunchPlanner, key: str, offset: int) -> None:
        super().__init__(planner, key)
        self._offset = offset

    def _meal(self) -> dict[str, Any] | None:
        return self.planner.meal_for(self.planner.today() + timedelta(days=self._offset))

    @property
    def native_value(self) -> str | None:
        meal = self._meal()
        return meal_title(meal)[:255] if meal else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        meal = self._meal()
        return _meal_attributes(meal) if meal else None


class ShoppingSensor(LunchPlannerEntity, SensorEntity):
    """The next day with a shopping list, and what is on it."""

    _attr_device_class = SensorDeviceClass.DATE

    @property
    def native_value(self) -> date | None:
        upcoming = self.planner.next_shopping()
        return upcoming[0] if upcoming else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        upcoming = self.planner.next_shopping()
        if not upcoming:
            return None
        _, meals = upcoming
        return {
            "meal_dates": [m["date"] for m in meals],
            "meals": [meal_title(m) for m in meals],
            "shopping_items": meal_shopping_items(meals),
        }
