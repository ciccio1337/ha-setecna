"""Time Setecna: ora delle 6 fasce dell'editor orologi."""
from __future__ import annotations
from datetime import time
from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .clocks import SLOTS
from .const import DOMAIN, CONF_SYSTEM_ID
from .entity import EditorEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    sid = entry.data[CONF_SYSTEM_ID]
    if coord.clock_editor.names:
        add(EditorSlotTime(coord, sid, i) for i in range(SLOTS))


class EditorSlotTime(EditorEntity, TimeEntity):
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, system_id, i: int) -> None:
        super().__init__(coordinator, system_id, f"clock_editor_slot_{i + 1}_time",
                         f"Editor orologi fascia {i + 1} ora")
        self._i = i

    @property
    def native_value(self) -> time | None:
        return self._ed.times[self._i]

    async def async_set_value(self, value: time) -> None:
        self._ed.set_time(self._i, value)
