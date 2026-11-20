"""Date Setecna: giorno/mese degli 8 slot del calendario stagionale.

La centralina memorizza solo giorno e mese (si ripete ogni anno): l'entità mostra la
prossima ricorrenza e, quando la imposti, l'anno viene ignorato.
"""
from __future__ import annotations
from datetime import date
from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from .clocks import SEASON_SLOTS, SeasonSlot, decode_season, encode_season, season_date, season_key
from .const import DOMAIN, CONF_SYSTEM_ID
from .entity import SetecnaExtraEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    sid = entry.data[CONF_SYSTEM_ID]
    add(SeasonDate(coord, sid, n) for n in SEASON_SLOTS)


class SeasonDate(SetecnaExtraEntity, DateEntity):
    _attr_icon = "mdi:calendar-star"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, system_id, n: int) -> None:
        super().__init__(coordinator, system_id, f"season_slot_{n}_date", f"Calendario stagionale {n} data")
        self._key = season_key(n)

    @property
    def available(self) -> bool:
        return super().available and self._key in self._d

    @property
    def native_value(self) -> date | None:
        return season_date(decode_season(self._d.get(self._key)), dt_util.now().date())

    @property
    def extra_state_attributes(self):
        s = decode_season(self._d.get(self._key))
        return {"giorno_mese": f"{s.day:02d}/{s.month:02d}" if s.used else None}

    async def async_set_value(self, value: date) -> None:
        s = decode_season(self._d.get(self._key))
        new = SeasonSlot(value.day, value.month, s.clima, s.acs, s.vmc)
        await self.coordinator.async_push(self._key, encode_season(new))
