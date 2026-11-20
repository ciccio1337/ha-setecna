"""Setecna REG integration (cloud s5a.eu, no MQTT)."""
from __future__ import annotations
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import SetecnaClient
from .clock_editor import ClockEditor
from .clocks import DAY_GROUPS, DAY_KEYS, KEY_TO_MODE, LABEL_TO_MODE, SLOTS, Slot, program_writes
from .coordinator import SetecnaCoordinator
from .const import DOMAIN, CONF_SYSTEM_ID
from .snapshot import async_register_snapshot_services

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SELECT,
             Platform.CLIMATE, Platform.CALENDAR, Platform.TIME, Platform.BUTTON,
             Platform.DATE, Platform.SWITCH]

_MODES = sorted((set(KEY_TO_MODE) | set(LABEL_TO_MODE)) - {"unused", "non usata"})
_DAYS = DAY_KEYS + list(DAY_GROUPS)

SET_PROGRAM_SCHEMA = vol.Schema({
    vol.Required("clock"): cv.string,
    vol.Optional("system_id"): cv.string,
    vol.Required("days"): vol.All(cv.ensure_list, [vol.In(_DAYS)]),
    vol.Required("slots"): vol.All(cv.ensure_list, vol.Length(max=SLOTS), [vol.Schema({
        vol.Required("time"): cv.time,
        vol.Required("mode"): vol.In(_MODES),
    })]),
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = SetecnaClient(session, entry.data[CONF_SYSTEM_ID],
                           entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = SetecnaCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.clock_editor = ClockEditor(coordinator)
    entry.async_on_unload(coordinator.async_add_listener(coordinator.clock_editor.on_coordinator_update))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_snapshot_services(hass, coordinator)
    _register_clock_service(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


def _register_clock_service(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "set_clock_program"):
        return

    async def set_clock_program(call: ServiceCall) -> None:
        coords = list(hass.data.get(DOMAIN, {}).values())
        if sid := call.data.get("system_id"):
            coords = [c for c in coords if c.client._sid == sid]
        if len(coords) != 1:
            raise ServiceValidationError("Indica system_id: ci sono più sistemi Setecna (o nessuno)")
        coord = coords[0]
        names = coord.clock_editor.names
        wanted = call.data["clock"].strip()
        clock = next((c for c, n in names.items() if n.casefold() == wanted.casefold()), None)
        if clock is None and wanted.isdigit() and int(wanted) in names:
            clock = int(wanted)
        if clock is None:
            raise ServiceValidationError(f"Orologio '{wanted}' non trovato: {', '.join(names.values())}")
        days: list[int] = []
        for d in call.data["days"]:
            for i in (DAY_GROUPS[d] if d in DAY_GROUPS else [DAY_KEYS.index(d)]):
                if i not in days:
                    days.append(i)
        slots = [Slot(KEY_TO_MODE.get(s["mode"], LABEL_TO_MODE.get(s["mode"])), s["time"].replace(second=0))
                 for s in sorted(call.data["slots"], key=lambda s: s["time"])]
        writes = program_writes(coord.data or {}, clock, days, slots)
        await coord.async_push_many(writes)

    hass.services.async_register(DOMAIN, "set_clock_program", set_clock_program, schema=SET_PROGRAM_SCHEMA)
