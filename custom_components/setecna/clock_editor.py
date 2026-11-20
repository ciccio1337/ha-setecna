"""Editor degli orologi: bozza di un giorno di un orologio, modificabile da HA.

Riproduce la scheda "Orologi" del portale con entità native: scegli orologio e giorno,
modifichi le 6 fasce (ora + modo) e poi applichi a uno o più giorni. Finché la bozza non
ha modifiche segue i dati della centralina; con modifiche in sospeso non viene
sovrascritta dagli aggiornamenti periodici.
"""
from __future__ import annotations

from datetime import time
from typing import Callable

from .clocks import (
    DAY_GROUPS, DAYS, MODE_COMFORT, MODE_UNUSED, SLOTS, Slot,
    clocks_present, day_slots, program_writes,
)
from .params import descr_label


def clock_names(raw: dict) -> dict[int, str]:
    """Nome di ogni orologio presente, dal descrittore MTx_DESCR (univoco)."""
    names: dict[int, str] = {}
    for c in clocks_present(raw):
        names[c] = descr_label(raw, f"MT{c}_DESCR") or f"Orologio {c}"
    seen: dict[str, int] = {}
    for n in names.values():
        seen[n] = seen.get(n, 0) + 1
    return {c: (n if seen[n] == 1 else f"{n} ({c})") for c, n in names.items()}


class ClockEditor:
    def __init__(self, coordinator) -> None:
        self._coord = coordinator
        raw = coordinator.data or {}
        self.names = clock_names(raw)
        self.clock: int | None = next(iter(self.names), None)
        self.day = 0
        self.times: list[time | None] = [None] * SLOTS
        self.modes: list[int] = [MODE_UNUSED] * SLOTS
        self.dirty = False
        self._listeners: list[Callable[[], None]] = []
        self._load()

    # ---------------------------------------------------------------- ascolto
    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb) if cb in self._listeners else None

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    def on_coordinator_update(self) -> None:
        """Nuovi dati dalla centralina: ricarica solo se non ci sono modifiche in sospeso."""
        if not self.dirty:
            self._load()
            self._notify()

    # ------------------------------------------------------------------ bozza
    def _load(self) -> None:
        if self.clock is None:
            return
        slots = day_slots(self._coord.data or {}, self.clock, self.day)
        self.times = [s.at for s in slots]
        self.modes = [s.mode for s in slots]
        self.dirty = False

    def reload(self) -> None:
        self._load()
        self._notify()

    def select_clock(self, clock: int) -> None:
        self.clock = clock
        self.reload()

    def select_day(self, day: int) -> None:
        self.day = day
        self.reload()

    def set_time(self, i: int, value: time) -> None:
        self.times[i] = value.replace(second=0, microsecond=0)
        if self.modes[i] == MODE_UNUSED:
            self.modes[i] = MODE_COMFORT  # dare un'ora a una fascia vuota la attiva
        self.dirty = True
        self._notify()

    def set_mode(self, i: int, mode: int) -> None:
        self.modes[i] = mode
        if mode != MODE_UNUSED and self.times[i] is None:
            self.times[i] = time(0, 0)
        self.dirty = True
        self._notify()

    def draft(self) -> list[Slot]:
        return [Slot(m, t if m != MODE_UNUSED else None) for t, m in zip(self.times, self.modes)]

    # ---------------------------------------------------------------- scrittura
    def writes_for(self, target: str) -> dict[str, str]:
        """target: "day" (giorno selezionato) oppure una chiave di DAY_GROUPS."""
        if self.clock is None:
            return {}
        days = [self.day] if target == "day" else DAY_GROUPS[target]
        return program_writes(self._coord.data or {}, self.clock, days, self.draft())

    async def apply(self, target: str) -> int:
        writes = self.writes_for(target)
        await self._coord.async_push_many(writes)
        self.dirty = False
        self._notify()
        return len(writes)


__all__ = ["ClockEditor", "clock_names", "DAYS"]
