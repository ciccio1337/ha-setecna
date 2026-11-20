"""Calendar Setecna: il programma settimanale di ogni orologio come eventi (sola lettura)."""
from __future__ import annotations
from datetime import datetime, timedelta
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from .clocks import MODE_LABELS, segments
from .const import DOMAIN, CONF_SYSTEM_ID
from .entity import SetecnaExtraEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    sid = entry.data[CONF_SYSTEM_ID]
    add(ClockCalendar(coord, sid, c, n) for c, n in coord.clock_editor.names.items())


class ClockCalendar(SetecnaExtraEntity, CalendarEntity):
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, system_id, clock: int, name: str) -> None:
        super().__init__(coordinator, system_id, f"clock_{clock}_calendar", f"Orologio {name}")
        self._clock = clock
        self._label = name

    def _events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        start, end = dt_util.as_local(start), dt_util.as_local(end)
        return [
            CalendarEvent(start=a, end=b, summary=MODE_LABELS[m].capitalize(),
                          description=f"Orologio {self._label}")
            for a, b, m in segments(self._d, self._clock, start, end)
        ]

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        ev = self._events(now, now + timedelta(seconds=1))
        return ev[0] if ev else None

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime,
                               end_date: datetime) -> list[CalendarEvent]:
        return self._events(start_date, end_date)
