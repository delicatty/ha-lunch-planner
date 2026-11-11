"""The drawn plan as a calendar."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import LunchPlannerConfigEntry
from .entity import LunchPlannerEntity
from .planner import meal_title


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LunchPlannerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([PlanCalendar(entry.runtime_data, "plan")])


def _event(meal: dict[str, Any]) -> CalendarEvent:
    day = date.fromisoformat(meal["date"])
    description = "\n".join(
        f"{p['name']}: {', '.join(p['ingredients'])}"
        if p.get("ingredients") and p["ingredients"] != [p["name"]]
        else p["name"]
        for p in meal["parts"]
    )
    return CalendarEvent(
        start=day,
        end=day + timedelta(days=1),
        summary=meal_title(meal),
        description=description,
        uid=meal["date"],
    )


class PlanCalendar(LunchPlannerEntity, CalendarEntity):
    """All-day events, one per planned lunch."""

    @property
    def event(self) -> CalendarEvent | None:
        """Today's lunch, or the next one."""
        today = self.planner.today().isoformat()
        for iso in sorted(self.planner.plan):
            if iso >= today:
                return _event(self.planner.plan[iso])
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        events = []
        for iso, meal in sorted(self.planner.plan.items()):
            day = date.fromisoformat(iso)
            day_start = dt_util.start_of_local_day(day)
            day_end = dt_util.start_of_local_day(day + timedelta(days=1))
            if day_start < end_date and day_end > start_date:
                events.append(_event(meal))
        return events
