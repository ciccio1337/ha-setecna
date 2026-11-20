"""Sensori Setecna."""
from __future__ import annotations
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from .const import DOMAIN, CONF_SYSTEM_ID
from .clocks import DAY_LABELS, MODE_LABELS, next_change, scheduled_mode, week_program
from .entity import EditorEntity, SetecnaEntity, SetecnaExtraEntity
from .params import build_param_map, display_value


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    sid = entry.data[CONF_SYSTEM_ID]
    pmap = build_param_map(coord.data or {})
    ents: list[SensorEntity] = [SetecnaSensor(coord, sid, p) for p in pmap.values() if p.entity_type == "sensor"]
    names = coord.clock_editor.names
    ents += [ClockNextChangeSensor(coord, sid, c, n) for c, n in names.items()]
    if names:
        ents.append(EditorStatusSensor(coord, sid))
    add(ents)


class ClockNextChangeSensor(SetecnaExtraEntity, SensorEntity):
    """Prossimo cambio di modo del programma settimanale (forzature escluse)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-end"

    def __init__(self, coordinator, system_id, clock: int, name: str) -> None:
        super().__init__(coordinator, system_id, f"clock_{clock}_next_change",
                         f"Orologio {name} prossimo cambio")
        self._clock = clock

    @property
    def native_value(self):
        nxt = next_change(self._d, self._clock, dt_util.now())
        return nxt[0] if nxt else None

    @property
    def extra_state_attributes(self):
        now = dt_util.now()
        nxt = next_change(self._d, self._clock, now)
        cur = scheduled_mode(self._d, self._clock, now)
        return {
            "orologio": self._clock,
            "modo_programmato": MODE_LABELS[cur] if cur is not None else None,
            "modo_successivo": MODE_LABELS[nxt[1]] if nxt else None,
            "programma": week_program(self._d, self._clock),
        }


class EditorStatusSensor(EditorEntity, SensorEntity):
    """Stato della bozza dell'editor: allineata alla centralina o con modifiche da applicare."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["allineato", "modifiche da applicare"]

    def __init__(self, coordinator, system_id) -> None:
        super().__init__(coordinator, system_id, "clock_editor_status", "Editor orologi stato")

    @property
    def icon(self):
        return "mdi:content-save-alert" if self._ed.dirty else "mdi:check-circle-outline"

    @property
    def native_value(self):
        return "modifiche da applicare" if self._ed.dirty else "allineato"

    @property
    def extra_state_attributes(self):
        ed = self._ed
        return {
            "orologio": ed.names.get(ed.clock),
            "giorno": DAY_LABELS[ed.day],
            "fasce": [
                {"fascia": i + 1, "ora": t.strftime("%H:%M") if t and m else None, "modo": MODE_LABELS[m]}
                for i, (t, m) in enumerate(zip(ed.times, ed.modes))
            ],
            "scritture_giorno": len(ed.writes_for("day")),
        }


class SetecnaSensor(SetecnaEntity, SensorEntity):
    def __init__(self, coordinator, system_id, param) -> None:
        super().__init__(coordinator, system_id, param)
        self._attr_device_class = param.device_class
        self._attr_native_unit_of_measurement = param.unit
        self._attr_state_class = param.state_class
        if param.transform == "enum" and param.enum_map:
            self._attr_options = list(dict.fromkeys(param.enum_map.values()))

    @property
    def native_value(self):
        raw = self._raw
        if raw is None:
            return None
        if self._param.transform == "timestamp":
            return dt_util.parse_datetime(raw)
        return display_value(self._param, raw)
