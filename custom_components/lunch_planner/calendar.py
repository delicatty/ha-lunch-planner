"""The drawn plan as a calendar."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import LunchPlannerConfigEntry
from .entity import LunchPlannerEntity
from .manager import LunchPlanner


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LunchPlannerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([PlanCalendar(entry.runtime_data, "plan")])


def _event(planner: LunchPlanner, meal: dict[str, Any]) -> CalendarEvent:
    start, end = planner.lunch_times(meal)
    description = "\n".join(
        f"{p['name']}: {', '.join(p['ingredients'])}"
        if p.get("ingredients") and p["ingredients"] != [p["name"]]
        else p["name"]
        for p in meal["parts"]
    )
    return CalendarEvent(
        start=start,
        end=end,
        summary=planner.event_title(meal),
        description=description,
        uid=meal["date"],
    )


class PlanCalendar(LunchPlannerEntity, CalendarEntity):
    """One event per planned lunch, at the lunch time from the options."""

    @property
    def event(self) -> CalendarEvent | None:
        """The lunch going on now, or the next one."""
        now = dt_util.now()
        for _, meal in sorted(self.planner.plan.items()):
            event = _event(self.planner, meal)
            if event.end > now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        events = []
        for _, meal in sorted(self.planner.plan.items()):
            event = _event(self.planner, meal)
            if event.start < end_date and event.end > start_date:
                events.append(event)
        return events
