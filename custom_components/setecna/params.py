"""Modello parametri Setecna → entità HA.

Porting fedele di models/attributes.go dell'addon Ingordigia.
Le trasformazioni jinja dell'addon sono qui tipizzate (div10/mul10/binary/
enum/signed_power) perché controlliamo entrambi i lati in Python.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from . import circuits as circ

# enum maps (raw -> label)
ZONE_MODE = {"0": "off", "2": "economy", "3": "comfort",
             "4": "forced off", "6": "forced economy", "23": "forced comfort"}
FORCING = {"0": "automatic", "1": "forced off", "2": "forced economy", "3": "forced comfort"}
FORCING_OPTS = ["automatic", "forced off", "forced economy", "forced comfort"]
FORCING_CMD = {"automatic": "0", "forced off": "1", "forced economy": "2", "forced comfort": "3"}
SEASON = {"0": "winter", "1": "summer"}
CAL_MODE = {"1": "off", "2": "economy", "3": "comfort"}
# forzatura velocità deumidificatore (D{i}_USER_SPEED_CONTROL)
FORCE_SPEED = {"0": "automatica", "1": "bassa", "2": "media", "3": "alta"}
FORCE_SPEED_OPTS = ["automatica", "bassa", "media", "alta"]
FORCE_SPEED_CMD = {"automatica": "0", "bassa": "1", "media": "2", "alta": "3"}


@dataclass
class ParamDef:
    key: str
    name: str
    entity_type: str                       # sensor|binary_sensor|number|select
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    transform: str | None = None           # div10|sdiv10|mul10|binary|signed_power|enum|timestamp|cmode|voutput|regtype
    options: list[str] | None = None
    enum_map: dict[str, str] | None = None  # raw -> label (display)
    cmd_map: dict[str, str] | None = None   # label -> raw (command)
    min: float | None = None
    max: float | None = None
    step: float | None = None
    zone: int | None = None                # indice zona (per device/climate grouping)


def _temp(key, name, **kw):
    return ParamDef(key, name, "sensor", device_class="temperature", unit="°C",
                    state_class="measurement", transform="sdiv10", **kw)


def _temp_num(key, name, mn, mx, step=0.1, **kw):
    return ParamDef(key, name, "number", device_class="temperature", unit="°C",
                    state_class="measurement", transform="sdiv10", min=mn, max=mx, step=step, **kw)


def _binary(key, name, **kw):
    return ParamDef(key, name, "binary_sensor", transform="binary", **kw)


# 32768/32769 (0x8000/0x8001) = sonda assente o non ancora letta
MISSING = ("32768", "32769")


# Tabella nomi predefiniti del portale (porting di jsZoneDesc in ows2/js/jq_orionws_bs.js)
_DESCR_NAMES = [
    "Zona", "Scala", "Soggiorno", "Cucina", "Salotto", "Camera", "Corridoio",
    "Disimpegno", "Bagno", "Bagno Vasca", "Bagno Doccia", "Lavanderia", "Ufficio",
    "Reception", "Magazzino", "Laboratorio", "Ingresso", "Zona giorno", "Zona notte",
    "Sala da Pranzo", "Cameretta", "Studio", "Integrazione", "Termoarredo",
]


def descr_label(raw: dict[str, str], key: str) -> str | None:
    """Decodifica un descrittore *_DESCR come fa il portale (jsZoneDesc).

    - 240-255 → _FREEDESC1-16 (nomi liberi), es. 247 → _FREEDESC8
    - 192-239 → _XFREEDESC1-48 (nomi liberi estesi), es. 192 → _XFREEDESC1
    - < 192   → tabella fissa: tipo = (code >> 3) & 0x1f, sottocodice = code & 7
                (es. 24 → "Cucina", 168 → "Studio", 42 → "Camera 2")
    """
    try:
        d = int(raw.get(key, "0"))
    except (ValueError, TypeError):
        return None
    if d <= 0:
        return None
    if d >= 240:
        return raw.get(f"_FREEDESC{d - 239}") or None
    if d >= 192:
        return raw.get(f"_XFREEDESC{d - 191}") or None
    kind, sub = (d >> 3) & 0x1F, d & 0x07
    if kind >= len(_DESCR_NAMES):
        return None  # "n.d." nel portale
    return _DESCR_NAMES[kind] + (f" {sub}" if sub else "")


def zone_label(raw: dict[str, str], zone: int) -> str | None:
    """Nome della zona dal suo descrittore Z{i}_DESCR."""
    return descr_label(raw, f"Z{zone}_DESCR")


def zone_regulated(raw: dict[str, str], zone: int) -> bool:
    """La zona pilota un circuito (CFG2 = circuito×16); 0 = sola sonda di lettura."""
    return raw.get(f"Z{zone}_CFG2", "0") != "0"


def build_param_map(raw: dict[str, str], read_only: bool = False) -> dict[str, ParamDef]:
    """Costruisce la mappa Id→ParamDef rispecchiando le condizioni dell'addon."""
    m: dict[str, ParamDef] = {}
    w = not read_only  # write abilitato

    def put(p: ParamDef):
        m[p.key] = p

    # --- last update ---
    put(ParamDef("LAST_UPDATE", "Last update", "sensor",
                 device_class="timestamp", transform="timestamp"))

    # --- globals ---
    put(_binary("GLOBAL_ENABLE", "Global state"))
    put(_temp("GLOBAL_T_EXT", "Global external temperature"))
    if w:
        # PATCH 2026-09-03: stagione scrivibile (estate/inverno) — usata dai profili "Fuori casa"
        put(ParamDef("GLOBAL_SEASON", "Global season", "select", transform="enum",
                     enum_map=SEASON, cmd_map={"winter": "0", "summer": "1"}, options=["winter", "summer"]))
    else:
        put(ParamDef("GLOBAL_SEASON", "Global season", "sensor",
                     device_class="enum", transform="enum", enum_map=SEASON))
    put(_binary("GLOBAL_DEICING", "Global de-ice state"))
    put(_temp("GLOBAL_EXPECTED_DEWP", "Global dewpoint"))
    if w:
        put(_temp_num("GLOBAL_ZONE_T_HYST", "Global zone temperature hysteresis", 0.1, 1))
        put(ParamDef("GLOBAL_ZONE_RH_HYST", "Global zone humidity hysteresis", "number",
                     device_class="humidity", unit="%", state_class="measurement",
                     transform="div10", min=1, max=5, step=0.1))
        put(_temp_num("GLOBAL_ZONE_DEICE_TRESH", "Global zone de-ice threshold", 6, 10))
    else:
        put(_temp("GLOBAL_ZONE_T_HYST", "Global zone temperature hysteresis"))
        put(ParamDef("GLOBAL_ZONE_RH_HYST", "Global zone humidity hysteresis", "sensor",
                     device_class="humidity", unit="%", state_class="measurement", transform="div10"))
        put(_temp("GLOBAL_ZONE_DEICE_TRESH", "Global zone de-ice threshold"))

    # --- domestic hot water ---
    put(_binary("ACS_MAIN_OUTPUT", "DHW state"))
    put(_binary("GLOBAL_ACS_ENABLE", "DHW enabled"))
    put(_temp("GLOBAL_T_ACS", "DHW temperature"))
    put(_temp("GLOBAL_SET_ACS", "DHW temperature setpoint"))
    if w:
        put(_temp_num("ACS_SET_ECONOMY", "DHW economy setpoint", 30, 60))
        put(_temp_num("ACS_SET_COMFORT", "DHW comfort setpoint", 30, 60))
        put(_temp_num("ACS_SET_HYST", "DHW setpoint hysteresis", 0, 10))
        put(_temp_num("ACS_SET_DELTA", "DHW second stage deviation", 0, 10))
    else:
        put(_temp("ACS_SET_ECONOMY", "DHW economy setpoint"))
        put(_temp("ACS_SET_COMFORT", "DHW comfort setpoint"))
        put(_temp("ACS_SET_HYST", "DHW setpoint hysteresis"))
        put(_temp("ACS_SET_DELTA", "DHW second stage deviation"))

    # --- analog inputs (1..8) ---
    for i in range(1, 9):
        if raw.get(f"FAIN{i}_TEMP") not in (None, *MISSING):
            put(_temp(f"FAIN{i}_TEMP", f"Analog input {i}"))

    # --- digital inputs (1..8) ---
    for i in range(1, 9):
        put(_binary(f"FDIN{i}_STATUS", f"Digital input {i}"))

    # --- digital alarms (1..5) ---
    for i in range(1, 6):
        put(_binary(f"FALDIN{i}_STATUS", f"Alarm {i}"))

    # --- zones (1..32) ---
    for i in range(1, 33):
        if raw.get(f"Z{i}_SENSOR_CHN", "0") == "0":
            continue
        put(_temp(f"Z{i}_TEMP", f"Zone {i} temperature", zone=i))
        if not zone_regulated(raw, i):
            # sonda che legge ma non pilota (es. touchscreen spostato a "Ripostiglio")
            if raw.get(f"Z{i}_RH") not in (None, *MISSING):
                put(ParamDef(f"Z{i}_RH", f"Zone {i} humidity", "sensor", device_class="humidity",
                             unit="%", state_class="measurement", transform="div10", zone=i))
            continue
        put(_binary(f"Z{i}_OUTPUT", f"Zone {i} state", zone=i))
        # Z{i}_ZONE_MODE è un bitfield come C{i}_MODE: bit 0-1 = off/antigelo/economy/comfort,
        # bit 2 = forzato (verificato: 19/147 → comfort, 2 → economy, 4 → off forzato)
        put(ParamDef(f"Z{i}_ZONE_MODE", f"Zone {i} mode", "sensor", device_class="enum",
                     transform="cmode", options=circ.MODE_OPTIONS, zone=i))
        put(_temp(f"Z{i}_ZONE_SET", f"Zone {i} setpoint", zone=i))
        if w:
            put(ParamDef(f"Z{i}_FORCING", f"Zone {i} preset", "select", transform="enum",
                         enum_map=FORCING, cmd_map=FORCING_CMD, options=FORCING_OPTS, zone=i))
            put(_temp_num(f"Z{i}_SET_CW", f"Zone {i} C.W. setpoint", 15, 30, zone=i))
            put(_temp_num(f"Z{i}_SET_EW", f"Zone {i} E.W. setpoint", 15, 30, zone=i))
            put(_temp_num(f"Z{i}_SET_CS", f"Zone {i} C.S. setpoint", 15, 30, zone=i))
            put(_temp_num(f"Z{i}_SET_ES", f"Zone {i} E.S. setpoint", 15, 30, zone=i))
        else:
            put(ParamDef(f"Z{i}_FORCING", f"Zone {i} preset", "sensor",
                         device_class="enum", transform="enum", enum_map=FORCING, zone=i))
            put(_temp(f"Z{i}_SET_CW", f"Zone {i} C.W. setpoint", zone=i))
            put(_temp(f"Z{i}_SET_EW", f"Zone {i} E.W. setpoint", zone=i))
            put(_temp(f"Z{i}_SET_CS", f"Zone {i} C.S. setpoint", zone=i))
            put(_temp(f"Z{i}_SET_ES", f"Zone {i} E.S. setpoint", zone=i))
        if raw.get(f"Z{i}_RH") not in (None, *MISSING):
            put(ParamDef(f"Z{i}_RH", f"Zone {i} humidity", "sensor", device_class="humidity",
                         unit="%", state_class="measurement", transform="div10", zone=i))
            if w:
                put(ParamDef(f"Z{i}_SET_RH", f"Zone {i} humidity setpoint", "number",
                             device_class="humidity", unit="%", state_class="measurement",
                             transform="div10", min=40, max=70, step=0.1, zone=i))
            else:
                put(ParamDef(f"Z{i}_SET_RH", f"Zone {i} humidity setpoint", "sensor",
                             device_class="humidity", unit="%", state_class="measurement",
                             transform="div10", zone=i))

    # --- circuits (1..8) --- presenti se C{i}_XREF != 0, nome dal descrittore C{i}_DESCR
    # (le chiavi C{i}_TEMP/C{i}_SET restano quelle di prima: stessi unique_id)
    for i in circ.circuits_present(raw):
        cn = f"Circuito {descr_label(raw, f'C{i}_DESCR') or i}"
        put(ParamDef(f"C{i}_MODE", f"{cn} modo", "sensor", device_class="enum",
                     transform="cmode", options=circ.MODE_OPTIONS))
        if raw.get(f"C{i}_TEMP") not in (None, *MISSING):
            put(_temp(f"C{i}_TEMP", f"{cn} temperatura mandata"))
        put(_temp(f"C{i}_SET", f"{cn} set mandata"))
        if raw.get(f"C{i}_RET_TEMP") not in (None, *MISSING):
            put(_temp(f"C{i}_RET_TEMP", f"{cn} temperatura ritorno"))
        put(ParamDef(f"C{i}_OUTPUT", f"{cn} apertura valvola", "sensor", unit="%",
                     state_class="measurement", transform="voutput"))
        put(ParamDef(f"C{i}_CCW_TYPE", f"{cn} regolazione invernale", "sensor", transform="regtype"))
        put(ParamDef(f"C{i}_CCS_TYPE", f"{cn} regolazione estiva", "sensor", transform="regtype"))
        # limite di sicurezza mandata dell'impianto (C{i}_LIMIT_TEMP), se configurato
        lim = circ.d10(raw.get(f"C{i}_LIMIT_TEMP")) or 0
        hi_w = lim if lim >= 20 else 80
        corr = [("WINTER_CORR", "correzione inverno"), ("SUMMER_CORR", "correzione estate")]
        for suf, lbl in corr:
            if w:
                put(_temp_num(f"C{i}_{suf}", f"{cn} {lbl}", -10, 10, step=0.5))
            else:
                put(_temp(f"C{i}_{suf}", f"{cn} {lbl}"))
        for (se, lvl), _ in circ.CURVE_KEYS.items():
            for key, x in circ.curve_param_keys(i, se, lvl):
                fixed = key.endswith("_M")
                lbl = (f"{cn} curva {circ.SEASON_LABEL[se]} {lvl} "
                       + ("esterna -10 (punto fisso)" if fixed else f"esterna {x:+d}"))
                if w:
                    mn, mx = (5, 30) if se == "summer" else (10, hi_w)
                    put(_temp_num(key, lbl, mn, mx, step=0.5))
                else:
                    put(_temp(key, lbl))

    # --- sources (1..3) ---
    for i in range(1, 4):
        if raw.get(f"S{i}_DESCR", "0") != "0":
            put(_binary(f"S{i}_ENABLED", f"Source {i} enabled"))
            put(_binary(f"S{i}_OUTPUT", f"Source {i} state"))
            put(_binary(f"S{i}_AUXOUTPUT", f"Source {i} auxiliary state"))

    # --- deumidificatori (1..8): presenti se OUTPUT_DEUM != 255 ---
    # (l'addon li filtrava su SPEED_LOW/ECONOMY != 0, sbagliato per i tipi on/off)
    fan_speeds = {"LOW": "low", "MED": "medium", "HIGH": "high",
                  "BOOST": "boost", "ECONOMY": "economy", "COMFORT": "comfort"}
    for i in range(1, 9):
        if raw.get(f"D{i}_OUTPUT_DEUM", "255") == "255":
            continue
        # nome reale dal descrittore (come il portale), es. "VMC", "Cucina"
        nm = descr_label(raw, f"D{i}_DESCR") or f"Deumidificatore {i}"
        put(_binary(f"D{i}_OUTPUT_DEUM", f"{nm} deumidificazione"))
        put(_binary(f"D{i}_OUTPUT_RENEW", f"{nm} rinnovo aria"))
        put(_binary(f"D{i}_OUTPUT_VALV", f"{nm} valvola acqua"))
        put(_binary(f"D{i}_OUTPUT_INTG", f"{nm} integrazione"))
        put(ParamDef(f"D{i}_REQ", f"{nm} richiesta", "sensor", state_class="measurement"))
        # velocità corrente del ventilatore (uscita 0-10V; 65535 = uscita non configurata).
        # Stessa scala delle portate D{i}_SPEED_*: l'unità dipende da come l'installatore
        # ha configurato il dispositivo (m³/h su una VMC, % su un fancoil) → nessuna unità qui.
        if raw.get(f"D{i}_OUTPUT_010", "65535") != "65535":
            put(ParamDef(f"D{i}_OUTPUT_010", f"{nm} velocità corrente", "sensor",
                         state_class="measurement", transform="uint16"))
        # forzatura velocità (Automatica/Bassa/Media/Alta) — scrivibile
        if w:
            put(ParamDef(f"D{i}_USER_SPEED_CONTROL", f"{nm} forzatura velocità", "select",
                         transform="enum", enum_map=FORCE_SPEED, cmd_map=FORCE_SPEED_CMD,
                         options=FORCE_SPEED_OPTS))
        else:
            put(ParamDef(f"D{i}_USER_SPEED_CONTROL", f"{nm} forzatura velocità", "sensor",
                         device_class="enum", transform="enum", enum_map=FORCE_SPEED))
        # portate solo se realmente configurate (0/254/255 = non usate)
        for code, lbl in fan_speeds.items():
            key = f"D{i}_SPEED_{code}"
            if raw.get(key, "0") not in ("0", "254", "255"):
                # Valore grezzo così come impostato sulla centralina (byte, 254/255 riservati).
                # L'unità dipende dall'impianto: % per un ventilatore (es. MTIO0300: 50/70/100),
                # m³/h per una VMC con setpoint di portata (es. 60/80/140) → nessuna unità.
                if w:
                    put(ParamDef(key, f"{nm} velocità {lbl}", "number",
                                 state_class="measurement", min=0, max=253, step=5))
                else:
                    put(ParamDef(key, f"{nm} velocità {lbl}", "sensor",
                                 state_class="measurement"))

    # --- energy meters (1..4) --- (solo se configurati: DESCR != 0)
    for i in range(1, 5):
        if raw.get(f"EM{i}_DESCR", "0") == "0":
            continue
        put(ParamDef(f"EM{i}_INSTANT", f"Energy meter {i} power", "sensor",
                     device_class="power", unit="kW", state_class="measurement", transform="signed_power"))
        put(ParamDef(f"EM{i}_ACCLO", f"Energy meter {i} total energy import", "sensor",
                     device_class="energy", unit="kWh", state_class="total_increasing", transform="div10"))
        if i == 4:
            put(ParamDef(f"EM{i}_ACC2LO", f"Energy meter {i} total energy export", "sensor",
                         device_class="energy", unit="kWh", state_class="total_increasing", transform="div10"))

    # --- orologi / calendars (1..8) --- nome reale dal descrittore MTx_DESCR
    for i in range(1, 9):
        if raw.get(f"MT{i}_XREF", "0") == "0":
            continue
        cn = f"Orologio {descr_label(raw, f'MT{i}_DESCR') or i}"
        put(ParamDef(f"MT{i}_MODE", f"{cn} modo attuale", "sensor",
                     device_class="enum", transform="enum", enum_map=CAL_MODE))
        if w:
            put(ParamDef(f"MT{i}_FORCING", f"{cn} forzatura", "select", transform="enum",
                         enum_map=FORCING, cmd_map=FORCING_CMD, options=FORCING_OPTS))
        else:
            put(ParamDef(f"MT{i}_FORCING", f"{cn} forzatura", "sensor",
                         device_class="enum", transform="enum", enum_map=FORCING))

    return m


def display_value(p: ParamDef, raw: str):
    """Trasforma il valore grezzo nel valore mostrato/usato da HA."""
    if raw is None or raw == "":
        return None
    t = p.transform
    # 32768/32769 = sensore assente/non collegato → non disponibile
    # (32768 compare per un ciclo quando si collega una sonda nuova: 3276,8 °C)
    if t in ("div10", "sdiv10", "mul10", "signed_power") and raw in MISSING:
        return None
    try:
        if t == "sdiv10":
            return circ.d10(raw)
        if t == "cmode":
            return circ.mode_label(raw)
        if t == "voutput":
            return circ.valve_percent(raw)
        if t == "regtype":
            return circ.reg_type(raw)
        if t == "div10":
            return round(int(raw) / 10, 1)
        if t == "mul10":
            return int(raw) * 10
        if t == "uint16":
            v = int(raw)
            return v if 0 <= v < 65535 else None  # 65535 = uscita non configurata
        if t == "binary":
            return raw == "1"
        if t == "enum":
            return p.enum_map.get(raw, raw)
        if t == "signed_power":
            v = int(raw)
            return round((v - 65536) / 100 if v >= 32768 else v / 100, 2)
        if t == "timestamp":
            return raw  # già ISO dal coordinator
    except (ValueError, TypeError):
        return None
    return raw


def command_value(p: ParamDef, value) -> str:
    """Trasforma il valore HA nel valore grezzo da inviare (putmprop)."""
    t = p.transform
    if p.entity_type == "select" and p.cmd_map:
        return p.cmd_map.get(value, "0")
    if t == "div10":
        return str(int(round(float(value) * 10)))
    if t == "sdiv10":
        v = int(round(float(value) * 10))
        return str(v + 65536 if v < 0 else v)  # int16 in complemento a due, come il portale
    if t == "mul10":
        return str(int(float(value) / 10))
    return str(value)
