"""Switch Setecna: calendario stagionale (abilitazione, ACS e VMC per slot)."""
from __future__ import annotations
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .clocks import SEASON_SLOTS, SeasonSlot, decode_season, encode_season, season_key
from .const import DOMAIN, CONF_SYSTEM_ID
from .entity import SetecnaExtraEntity

ENABLE_KEY = "P_CALENDAR_ENABLE"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    sid = entry.data[CONF_SYSTEM_ID]
    ents: list[SwitchEntity] = [SeasonEnableSwitch(coord, sid)]
    for n in SEASON_SLOTS:
        ents += [SeasonFlagSwitch(coord, sid, n, "acs"), SeasonFlagSwitch(coord, sid, n, "vmc")]
    add(ents)


class SeasonEnableSwitch(SetecnaExtraEntity, SwitchEntity):
    _attr_icon = "mdi:calendar-sync"

    def __init__(self, coordinator, system_id) -> None:
        super().__init__(coordinator, system_id, "season_calendar_enable", "Calendario stagionale")

    @property
    def available(self) -> bool:
        return super().available and ENABLE_KEY in self._d

    @property
    def is_on(self):
        return self._d.get(ENABLE_KEY) == "1"

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_push(ENABLE_KEY, "1")

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_push(ENABLE_KEY, "0")


class SeasonFlagSwitch(SetecnaExtraEntity, SwitchEntity):
    """ACS o VMC accesa/spenta dalla data dello slot."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, system_id, n: int, flag: str) -> None:
        label = {"acs": "ACS", "vmc": "VMC"}[flag]
        super().__init__(coordinator, system_id, f"season_slot_{n}_{flag}",
                         f"Calendario stagionale {n} {label}")
        self._key = season_key(n)
        self._flag = flag
        self._attr_icon = "mdi:water-boiler" if flag == "acs" else "mdi:fan"

    @property
    def available(self) -> bool:
        return super().available and self._key in self._d

    @property
    def is_on(self):
        return getattr(decode_season(self._d.get(self._key)), self._flag)

    async def _set(self, on: bool) -> None:
        s = decode_season(self._d.get(self._key))
        if not s.used:
            raise HomeAssistantError("Slot non usato: imposta prima la data")
        new = SeasonSlot(s.day, s.month, s.clima,
                         on if self._flag == "acs" else s.acs,
                         on if self._flag == "vmc" else s.vmc)
        await self.coordinator.async_push(self._key, encode_season(new))

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
