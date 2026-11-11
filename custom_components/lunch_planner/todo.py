"""The meal database as five editable to-do lists.

Item name = the meal part. Description = what to buy, one thing per line or
separated by commas, plus an optional ``season: 5-7`` line. A ticked-off item
stays in the database but is not drawn.
"""

from __future__ import annotations

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LunchPlannerConfigEntry
from .const import CATEGORIES
from .entity import LunchPlannerEntity
from .manager import LunchPlanner


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LunchPlannerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(CatalogList(entry.runtime_data, c) for c in CATEGORIES)


class CatalogList(LunchPlannerEntity, TodoListEntity):
    """One category of the meal database."""

    # Kept out of the To-do panel: the Lunch planner panel shows these lists.
    _attr_entity_registry_visible_default = False
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.MOVE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, planner: LunchPlanner, category: str) -> None:
        super().__init__(planner, category)
        self._category = category

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                summary=i["summary"],
                uid=i["uid"],
                status=TodoItemStatus.COMPLETED if i["done"] else TodoItemStatus.NEEDS_ACTION,
                description=i["description"] or None,
            )
            for i in self.planner.items[self._category]
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        self.planner.add_item(
            self._category,
            item.summary or "",
            item.description,
            item.status == TodoItemStatus.COMPLETED,
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        self.planner.update_item(
            self._category,
            item.uid,
            item.summary or "",
            item.description,
            item.status == TodoItemStatus.COMPLETED,
        )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        self.planner.delete_items(self._category, uids)

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        self.planner.move_item(self._category, uid, previous_uid)
