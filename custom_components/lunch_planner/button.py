"""Button: draw the upcoming lunches again."""

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
    async_add_entities([RedrawButton(entry.runtime_data, "redraw")])


class RedrawButton(LunchPlannerEntity, ButtonEntity):
    """Draw again every upcoming lunch whose shopping day has not come yet."""

    async def async_press(self) -> None:
        await self.planner.async_redraw()
