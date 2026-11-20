"""Select Setecna (preset/forzature, editor orologi, calendario stagionale)."""
from __future__ import annotations
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .clocks import (
    DAY_LABELS, LABEL_TO_MODE, MODE_LABELS, SEASON_CLIMA, SEASON_CLIMA_OPTIONS,
    SEASON_SLOTS, SEASON_UNUSED, SLOT_MODE_OPTIONS, SLOTS, SeasonSlot,
    decode_season, encode_season, season_key,
)
from .const import DOMAIN, CONF_SYSTEM_ID
from .entity import EditorEntity, SetecnaEntity, SetecnaExtraEntity
from .params import build_param_map, display_value, command_value


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    sid = entry.data[CONF_SYSTEM_ID]
    pmap = build_param_map(coord.data or {})
    ents: list[SelectEntity] = [SetecnaSelect(coord, sid, p) for p in pmap.values() if p.entity_type == "select"]
    if coord.clock_editor.names:
        ents += [EditorClockSelect(coord, sid), EditorDaySelect(coord, sid)]
        ents += [EditorSlotModeSelect(coord, sid, i) for i in range(SLOTS)]
    ents += [SeasonClimaSelect(coord, sid, n) for n in SEASON_SLOTS]
    add(ents)


class SetecnaSelect(SetecnaEntity, SelectEntity):
    def __init__(self, coordinator, system_id, param) -> None:
        super().__init__(coordinator, system_id, param)
        self._attr_options = param.options or []

    @property
    def current_option(self):
        raw = self._raw
        return None if raw is None else display_value(self._param, raw)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_push(self._param.key, command_value(self._param, option))


# --------------------------------------------------------------- editor orologi
class EditorClockSelect(EditorEntity, SelectEntity):
    _attr_icon = "mdi:clock-edit-outline"

    def __init__(self, coordinator, system_id) -> None:
        super().__init__(coordinator, system_id, "clock_editor_clock", "Editor orologi orologio")
        self._attr_options = list(self._ed.names.values())

    @property
    def current_option(self):
        return self._ed.names.get(self._ed.clock)

    async def async_select_option(self, option: str) -> None:
        clock = next(c for c, n in self._ed.names.items() if n == option)
        self._ed.select_clock(clock)


class EditorDaySelect(EditorEntity, SelectEntity):
    _attr_icon = "mdi:calendar-week"
    _attr_options = DAY_LABELS

    def __init__(self, coordinator, system_id) -> None:
        super().__init__(coordinator, system_id, "clock_editor_day", "Editor orologi giorno")

    @property
    def current_option(self):
        return DAY_LABELS[self._ed.day]

    async def async_select_option(self, option: str) -> None:
        self._ed.select_day(DAY_LABELS.index(option))


class EditorSlotModeSelect(EditorEntity, SelectEntity):
    _attr_options = SLOT_MODE_OPTIONS

    def __init__(self, coordinator, system_id, i: int) -> None:
        super().__init__(coordinator, system_id, f"clock_editor_slot_{i + 1}_mode",
                         f"Editor orologi fascia {i + 1} modo")
        self._i = i

    @property
    def icon(self):
        return {0: "mdi:minus-circle-outline", 1: "mdi:power", 2: "mdi:leaf",
                3: "mdi:sofa"}.get(self._ed.modes[self._i], "mdi:clock-outline")

    @property
    def current_option(self):
        return MODE_LABELS[self._ed.modes[self._i]]

    async def async_select_option(self, option: str) -> None:
        self._ed.set_mode(self._i, LABEL_TO_MODE[option])


# --------------------------------------------------------- calendario stagionale
class SeasonClimaSelect(SetecnaExtraEntity, SelectEntity):
    """Climatizzazione dello slot (o "non usato" per svuotarlo)."""

    _attr_options = SEASON_CLIMA_OPTIONS
    _attr_icon = "mdi:sun-snowflake-variant"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, system_id, n: int) -> None:
        super().__init__(coordinator, system_id, f"season_slot_{n}_clima",
                         f"Calendario stagionale {n} climatizzazione")
        self._key = season_key(n)

    @property
    def available(self) -> bool:
        return super().available and self._key in self._d

    @property
    def current_option(self):
        s = decode_season(self._d.get(self._key))
        return SEASON_CLIMA[s.clima] if s.used else SEASON_UNUSED

    async def async_select_option(self, option: str) -> None:
        s = decode_season(self._d.get(self._key))
        if option == SEASON_UNUSED:
            new = SeasonSlot(0, 1, 0, False, False)
        else:
            clima = next(k for k, v in SEASON_CLIMA.items() if v == option)
            # slot vuoto: senza data non si può attivare → 1 gennaio come segnaposto
            new = SeasonSlot(s.day or 1, s.month if s.used else 1, clima, s.acs, s.vmc)
        await self.coordinator.async_push(self._key, encode_season(new))
