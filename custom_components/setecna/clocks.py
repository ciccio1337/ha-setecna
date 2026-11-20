"""Modello degli orologi (MT) e del calendario stagionale Setecna.

Reverse della scheda "Orologi" del portale s5a.eu (ows2/js/jq_orionws_bs.js):

* Orologi MT1..MT8, presenti se MTx_XREF != 0.
* Fascia MT{orologio}{giorno}{fascia}: giorno 0 = lunedì … 6 = domenica, fascia 0..5.
  valore = modo * 2048 + ore * 64 + minuti
  modo 0 = non usata, 1 = spento, 2 = economy, 3 = comfort
  (il portale scrive 0 quando il modo è "non usata").
  Ogni fascia vale "da quest'ora in poi" fino alla fascia successiva, anche a cavallo
  della mezzanotte; l'ordine delle fasce nella giornata non conta.
* MTx_MODE: modo attuale (1 spento, 2 economy, 3 comfort).
* MTx_FORCING: forzatura (0 automatico, 1 spento, 2 economy, 3 comfort).

Calendario stagionale (P_CALENDAR_SLOT_1..8, abilitato da P_CALENDAR_ENABLE):
  valore = clima << 14 | acs << 13 | vmc << 12 | mese << 8 | giorno
  clima 0 = off, 1 = inverno, 2 = estate, 3 = auto; giorno 0 = slot non usato.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

CLOCK_IDS = range(1, 9)
DAYS = 7
SLOTS = 6

MODE_UNUSED, MODE_OFF, MODE_ECO, MODE_COMFORT = 0, 1, 2, 3
MODE_KEYS = {MODE_UNUSED: "unused", MODE_OFF: "off", MODE_ECO: "economy", MODE_COMFORT: "comfort"}
MODE_LABELS = {MODE_UNUSED: "non usata", MODE_OFF: "spento", MODE_ECO: "economy", MODE_COMFORT: "comfort"}
LABEL_TO_MODE = {v: k for k, v in MODE_LABELS.items()}
KEY_TO_MODE = {v: k for k, v in MODE_KEYS.items()}
SLOT_MODE_OPTIONS = [MODE_LABELS[m] for m in (MODE_UNUSED, MODE_OFF, MODE_ECO, MODE_COMFORT)]

DAY_LABELS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_GROUPS = {"all": list(range(7)), "weekdays": list(range(5)), "weekend": [5, 6]}

SEASON_CLIMA = {0: "off", 1: "inverno", 2: "estate", 3: "auto"}
SEASON_UNUSED = "non usato"
SEASON_CLIMA_OPTIONS = [SEASON_UNUSED] + [SEASON_CLIMA[i] for i in range(4)]
SEASON_SLOTS = range(1, 9)


@dataclass(frozen=True)
class Slot:
    mode: int            # MODE_*
    at: time | None      # None se non usata

    @property
    def used(self) -> bool:
        return self.mode != MODE_UNUSED and self.at is not None


# ------------------------------------------------------------------ fasce
def slot_key(clock: int, day: int, slot: int) -> str:
    return f"MT{clock}{day}{slot}"


def decode_slot(raw) -> Slot:
    """Come la subscribe di .ows-mtime-prop: modo fuori range → fascia vuota."""
    try:
        bv = int(raw)
    except (TypeError, ValueError):
        return Slot(MODE_UNUSED, None)
    mode = bv // 2048
    if mode < 0 or mode > 3:
        return Slot(MODE_UNUSED, None)
    rest = bv % 2048
    hh, mm = rest // 64, rest % 64
    if not (0 <= hh < 24):
        hh = 0
    if not (0 <= mm < 60):
        mm = 0
    if mode == MODE_UNUSED:
        return Slot(MODE_UNUSED, None)
    return Slot(mode, time(hh, mm))


def encode_slot(slot: Slot) -> str:
    """Come SendMTimeData: modo 0 → valore 0."""
    if not slot.used:
        return "0"
    return str(slot.mode * 2048 + slot.at.hour * 64 + slot.at.minute)


def clock_present(raw: dict, clock: int) -> bool:
    return raw.get(f"MT{clock}_XREF", "0") not in ("0", None, "")


def clocks_present(raw: dict) -> list[int]:
    return [c for c in CLOCK_IDS if clock_present(raw, c)]


def day_slots(raw: dict, clock: int, day: int) -> list[Slot]:
    """Le 6 fasce del giorno nell'ordine in cui sono memorizzate."""
    return [decode_slot(raw.get(slot_key(clock, day, s))) for s in range(SLOTS)]


def normalize(slots: list[Slot]) -> list[Slot]:
    """Fasce usate ordinate per ora, poi le vuote (max 6). Doppioni di ora: vince l'ultima."""
    by_time: dict[time, Slot] = {}
    for s in slots:
        if s.used:
            by_time[s.at] = s
    used = [by_time[t] for t in sorted(by_time)]
    return (used + [Slot(MODE_UNUSED, None)] * SLOTS)[:SLOTS]


def program_writes(raw: dict, clock: int, days: list[int], slots: list[Slot]) -> dict[str, str]:
    """Parametri da scrivere per applicare `slots` ai `days` (solo quelli che cambiano).

    Le fasce restano nella posizione data (come fa il portale): la centralina non
    richiede un ordine, e riordinare causerebbe scritture inutili.
    """
    padded = (list(slots) + [Slot(MODE_UNUSED, None)] * SLOTS)[:SLOTS]
    out: dict[str, str] = {}
    for d in days:
        for s, sl in enumerate(padded):
            key = slot_key(clock, d, s)
            val = encode_slot(sl)
            if str(raw.get(key, "")) != val:
                out[key] = val
    return out


def week_program(raw: dict, clock: int) -> dict[str, list[dict]]:
    """Programma leggibile: {"lunedì": [{"ora": "08:00", "modo": "comfort"}, …], …}."""
    out = {}
    for d in range(DAYS):
        out[DAY_LABELS[d]] = [
            {"ora": s.at.strftime("%H:%M"), "modo": MODE_LABELS[s.mode]}
            for s in normalize(day_slots(raw, clock, d)) if s.used
        ]
    return out


# ------------------------------------------------------------ linea del tempo
def change_points(raw: dict, clock: int, start: datetime, end: datetime) -> list[tuple[datetime, int]]:
    """Cambi di modo (datetime locale, modo) da una settimana prima di `start` fino a `end`.

    `start`/`end` devono essere aware: le ore delle fasce sono interpretate nel loro fuso.
    Include almeno un punto ≤ start (se il programma ha fasce) per sapere il modo iniziale.
    """
    tz = start.tzinfo
    weekly = [normalize(day_slots(raw, clock, d)) for d in range(DAYS)]
    if not any(s.used for day in weekly for s in day):
        return []
    pts: list[tuple[datetime, int]] = []
    day = start.date() - timedelta(days=7)
    while day <= end.date():
        for s in weekly[day.weekday()]:
            if s.used:
                pts.append((datetime.combine(day, s.at, tzinfo=tz), s.mode))
        day += timedelta(days=1)
    pts.sort(key=lambda p: p[0])
    # elimina i cambi che non cambiano modo (prima di tagliare, così l'inizio reale resta)
    merged: list[tuple[datetime, int]] = []
    for t, m in pts:
        if not merged or merged[-1][1] != m:
            merged.append((t, m))
    # tieni l'ultimo punto ≤ start e tutti quelli successivi fino a end
    first = 0
    for i, (t, _) in enumerate(merged):
        if t <= start:
            first = i
    return [p for p in merged[first:] if p[0] <= end]


def segments(raw: dict, clock: int, start: datetime, end: datetime) -> list[tuple[datetime, datetime, int]]:
    """Intervalli [inizio, fine) con modo costante che intersecano [start, end)."""
    pts = change_points(raw, clock, start, end)
    out = []
    for i, (t, m) in enumerate(pts):
        nxt = pts[i + 1][0] if i + 1 < len(pts) else None
        if nxt is None:
            # estendi fino al prossimo cambio reale oltre `end` (al massimo 8 giorni)
            later = change_points(raw, clock, end, end + timedelta(days=8))
            nxt = next((p[0] for p in later if p[0] > end and p[1] != m), end + timedelta(days=8))
        if nxt > start and t < end:
            out.append((t, nxt, m))
    return out


def next_change(raw: dict, clock: int, now: datetime) -> tuple[datetime, int] | None:
    pts = change_points(raw, clock, now, now + timedelta(days=8))
    for t, m in pts:
        if t > now:
            return t, m
    return None


def scheduled_mode(raw: dict, clock: int, now: datetime) -> int | None:
    pts = change_points(raw, clock, now, now)
    return pts[0][1] if pts else None


# ------------------------------------------------------- calendario stagionale
@dataclass(frozen=True)
class SeasonSlot:
    day: int      # 0 = non usato
    month: int
    clima: int    # 0 off, 1 inverno, 2 estate, 3 auto
    acs: bool
    vmc: bool

    @property
    def used(self) -> bool:
        return self.day != 0


def season_key(n: int) -> str:
    return f"P_CALENDAR_SLOT_{n}"


def decode_season(raw) -> SeasonSlot:
    try:
        bv = int(raw)
    except (TypeError, ValueError):
        bv = 0
    day = bv & 0xFF
    if day == 0:
        return SeasonSlot(0, 1, 0, False, False)
    return SeasonSlot(day, (bv >> 8) & 0x0F, (bv >> 14) & 0x3, bool((bv >> 13) & 1), bool((bv >> 12) & 1))


def encode_season(s: SeasonSlot) -> str:
    """Come SendCalSlotData (mese 1..12, giorno 0..31; giorno 0 → 0)."""
    day = max(0, min(31, s.day))
    if day == 0:
        return "0"
    month = max(1, min(12, s.month))
    return str((s.clima << 14) | (int(s.acs) << 13) | (int(s.vmc) << 12) | (month << 8) | day)


def season_date(s: SeasonSlot, today: date) -> date | None:
    """Data della prossima ricorrenza (oggi compreso) — l'anno serve solo all'entità date."""
    if not s.used:
        return None
    for year in (today.year, today.year + 1):
        try:
            d = date(year, s.month, s.day)
        except ValueError:
            continue
        if d >= today:
            return d
    return None
