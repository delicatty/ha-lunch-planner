"""Base entity for Lunch Planner."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .manager import LunchPlanner


class LunchPlannerEntity(Entity):
    """An entity that belongs to one planner and updates with it."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, planner: LunchPlanner, key: str) -> None:
        self.planner = planner
        entry = planner.entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Lunch Planner",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.planner.async_add_listener(self.async_write_ha_state))
