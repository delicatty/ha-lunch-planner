"""Buttons: draw the upcoming lunches again, send the shopping list now."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LunchPlannerConfigEntry
from .entity import LunchPlannerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LunchPlannerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    planner = entry.runtime_data
    async_add_entities([RedrawButton(planner, "redraw"), ShoppingButton(planner, "send_shopping")])


class RedrawButton(LunchPlannerEntity, ButtonEntity):
    """Draw again every upcoming lunch whose shopping is not done yet."""

    async def async_press(self) -> None:
        drawn = self.planner.async_redraw()
        if drawn:
            await self.planner.async_send_plan(drawn)


class ShoppingButton(LunchPlannerEntity, ButtonEntity):
    """Send today's shopping list now, without waiting for the set time."""

    async def async_press(self) -> None:
        await self.planner.async_send_shopping()
