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
from .planner import meal_shopping_items


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
            ToBuySensor(planner, "to_buy"),
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
        return self.planner.describe(meal)[:255] if meal else None

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
            "meals": [self.planner.describe(m) for m in meals],
            "shopping_items": meal_shopping_items(meals),
        }


class ToBuySensor(LunchPlannerEntity, SensorEntity):
    """What to buy on the next shopping day, as one line of text.

    The state is cut at Home Assistant's 255-character limit; the
    ``shopping_items`` attribute always holds the whole list.
    """

    @property
    def native_value(self) -> str | None:
        upcoming = self.planner.next_shopping()
        if not upcoming:
            return None
        text = ", ".join(meal_shopping_items(upcoming[1]))
        return text if len(text) <= 255 else text[:254] + "…"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        upcoming = self.planner.next_shopping()
        if not upcoming:
            return None
        day, meals = upcoming
        lines = [
            f"{self.planner.day_label(date.fromisoformat(m['date']))}: {self.planner.describe(m)}"
            for m in meals
        ]
        morning = any(m["date"] == day.isoformat() for m in meals)
        return {
            "shopping_date": day.isoformat(),
            # Shopping in the morning of the lunch day (a long break before
            # it): the list goes out the evening before, on list_date.
            "shopping_morning": morning,
            "list_date": (day - timedelta(days=1) if morning else day).isoformat(),
            "meal_dates": [m["date"] for m in meals],
            "meals": [self.planner.describe(m) for m in meals],
            # One line per lunch, e.g. "pon 16.11: Zupa grzybowa", for messages.
            "summary": "\n".join(lines),
            "shopping_items": meal_shopping_items(meals),
        }
