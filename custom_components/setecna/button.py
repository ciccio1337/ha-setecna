"""Button Setecna: applica / annulla le modifiche dell'editor orologi."""
from __future__ import annotations
import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, CONF_SYSTEM_ID
from .entity import EditorEntity

_LOGGER = logging.getLogger(__name__)

# (target, suffisso, nome, icona)
_APPLY = [
    ("day", "apply_day", "Editor orologi applica al giorno", "mdi:content-save"),
    ("weekdays", "apply_weekdays", "Editor orologi applica lun-ven", "mdi:briefcase-outline"),
    ("weekend", "apply_weekend", "Editor orologi applica sab-dom", "mdi:beach"),
    ("all", "apply_all", "Editor orologi applica a tutti i giorni", "mdi:calendar-sync"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    sid = entry.data[CONF_SYSTEM_ID]
    if coord.clock_editor.names:
        ents: list[ButtonEntity] = [EditorApplyButton(coord, sid, *a) for a in _APPLY]
        ents.append(EditorReloadButton(coord, sid))
        add(ents)


class EditorApplyButton(EditorEntity, ButtonEntity):
    def __init__(self, coordinator, system_id, target, suffix, name, icon) -> None:
        super().__init__(coordinator, system_id, f"clock_editor_{suffix}", name)
        self._target = target
        self._attr_icon = icon

    async def async_press(self) -> None:
        n = await self._ed.apply(self._target)
        _LOGGER.info("Setecna orologio %s: %d fasce scritte (%s)",
                     self._ed.names.get(self._ed.clock), n, self._target)


class EditorReloadButton(EditorEntity, ButtonEntity):
    _attr_icon = "mdi:undo"

    def __init__(self, coordinator, system_id) -> None:
        super().__init__(coordinator, system_id, "clock_editor_reload", "Editor orologi annulla modifiche")

    async def async_press(self) -> None:
        self._ed.reload()
