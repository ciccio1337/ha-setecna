"""Circuiti di mandata (scheda *Circuiti* del portale): modo, valvola, curve climatiche.

Reverse di station/*#tab-circuit e ows2/js/jq_orionws_bs.js:
- presente se C{i}_XREF != 0; nome da C{i}_DESCR (jsZoneDesc)
- C{i}_MODE: bit 0-1 = off/antigelo/economy/comfort, bit 2 = forzato
- C{i}_OUTPUT (VOUTPUT): int16 / 10 / 16.384 = % valvola; -20000 = "CHIUSURA"
- C{i}_CCW_TYPE / C{i}_CCS_TYPE (TYPE_REGULATION): 0 punto fisso, 1 climatica 4 punti, …
- curva invernale C{i}_CCW{C|E}_{M,0,10,20}: mandata a -10/0/+10/+20 °C esterni (M = -10 o punto fisso)
- curva estiva    C{i}_CCS{C|E}_{10,20,30,40}: mandata a +10/+20/+30/+40 °C esterni
- correzioni C{i}_WINTER_CORR / C{i}_SUMMER_CORR; tutte le temperature int16 in decimi (D10)
"""
from __future__ import annotations

from html import escape

MISSING = ("32768", "32769")

MODE_LABELS = ["off", "antigelo", "economy", "comfort"]
MODE_OPTIONS = MODE_LABELS + [f"{m} (forzato)" for m in MODE_LABELS]

REG_TYPES = {0: "punto fisso", 1: "curva climatica", 2: "curva Kd", 3: "curva Kdm",
             40: "da sorgente 1", 41: "da sorgente 2", 42: "da sorgente 3",
             43: "da sonda mandata", 44: "da sonda ritorno", 45: "da setpoint ACS",
             46: "da math1", 47: "da math2", 48: "da math3"}
REG_TYPES.update({z: f"da zona {z - 7}" for z in range(8, 40)})

# (stagione, livello) → [(suffisso parametro, temperatura esterna)]
WINTER_X = [("M", -10), ("0", 0), ("10", 10), ("20", 20)]
SUMMER_X = [("10", 10), ("20", 20), ("30", 30), ("40", 40)]
CURVE_KEYS = {
    ("winter", "comfort"): ("CCWC", WINTER_X), ("winter", "economy"): ("CCWE", WINTER_X),
    ("summer", "comfort"): ("CCSC", SUMMER_X), ("summer", "economy"): ("CCSE", SUMMER_X),
}
SEASON_LABEL = {"winter": "inverno", "summer": "estate"}
LEVEL_LABEL = {"comfort": "comfort", "economy": "economy"}


def s16(raw) -> int | None:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    return v - 65536 if v >= 32768 else v


def d10(raw) -> float | None:
    """Temperatura D10 con segno; None se sonda assente."""
    if raw is None or str(raw) in MISSING:
        return None
    v = s16(raw)
    return None if v is None else round(v / 10, 1)


def circuits_present(raw: dict) -> list[int]:
    return [i for i in range(1, 9) if raw.get(f"C{i}_XREF", "0") not in ("0", "", None)]


def mode_label(raw) -> str | None:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    lbl = MODE_LABELS[v & 0x3]
    return f"{lbl} (forzato)" if v & 0x4 else lbl


def valve_percent(raw) -> float | None:
    v = s16(raw)
    if v is None or v == -20000:  # -20000 = comando di chiusura
        return None
    return round(v / 10 / 16.384, 1)


def reg_type(raw) -> str | None:
    try:
        return REG_TYPES.get(int(raw), "sconosciuto")
    except (TypeError, ValueError):
        return None


def season(raw: dict) -> str:
    return "summer" if raw.get("GLOBAL_SEASON") == "1" else "winter"


def curve_param_keys(i: int, season_: str, level: str) -> list[tuple[str, int]]:
    prefix, xs = CURVE_KEYS[(season_, level)]
    return [(f"C{i}_{prefix}_{suf}", x) for suf, x in xs]


def curve(raw: dict, i: int, season_: str, level: str) -> list[tuple[float, float]]:
    """Punti (T esterna, T mandata) della curva; punto fisso → linea piatta al primo valore."""
    pts = [(x, d10(raw.get(k))) for k, x in curve_param_keys(i, season_, level)]
    pts = [(x, y) for x, y in pts if y is not None]
    typ = s16(raw.get(f"C{i}_{'CCW' if season_ == 'winter' else 'CCS'}_TYPE"))
    if typ == 0 and pts:
        return [(pts[0][0], pts[0][1]), (pts[-1][0], pts[0][1])]
    return pts


def interpolate(points: list[tuple[float, float]], x: float) -> float | None:
    """Valore della curva a x (lineare tra i punti, costante oltre gli estremi)."""
    if not points:
        return None
    pts = sorted(points)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return round(y0 + (y1 - y0) * (x - x0) / (x1 - x0), 1)
    return None


def correction(raw: dict, i: int, season_: str) -> float:
    return d10(raw.get(f"C{i}_{'WINTER' if season_ == 'winter' else 'SUMMER'}_CORR")) or 0.0


def curve_info(raw: dict, i: int) -> dict:
    """Riassunto per attributi e grafico: curva della stagione attiva e punto di lavoro."""
    se = season(raw)
    text = d10(raw.get("GLOBAL_T_EXT"))
    corr = correction(raw, i, se)
    out = {"stagione": SEASON_LABEL[se], "temperatura_esterna": text, "correzione": corr,
           "tipo_regolazione": reg_type(raw.get(f"C{i}_{'CCW' if se == 'winter' else 'CCS'}_TYPE")),
           "set_mandata": d10(raw.get(f"C{i}_SET")), "mandata": d10(raw.get(f"C{i}_TEMP")),
           "modo": mode_label(raw.get(f"C{i}_MODE"))}
    for lvl in ("comfort", "economy"):
        pts = curve(raw, i, se, lvl)
        out[f"curva_{lvl}"] = [{"esterna": x, "mandata": y} for x, y in pts]
        v = interpolate(pts, text) if text is not None else None
        out[f"set_curva_{lvl}"] = round(v + corr, 1) if v is not None else None
    return out


# --------------------------------------------------------------------------- SVG
_W, _H = 640, 360
_ML, _MR, _MT, _MB = 52, 18, 18, 46
_COL = {"comfort": "#e8833a", "economy": "#3a9d6b", "axis": "#8a8f98", "now": "#4a7fd6"}


def render_svg(raw: dict, i: int, name: str) -> bytes:
    info = curve_info(raw, i)
    se = season(raw)
    xmin, xmax = (-15, 25) if se == "winter" else (5, 45)
    curves = {lvl: curve(raw, i, se, lvl) for lvl in ("comfort", "economy")}
    corr = info["correzione"]
    ys = [y + corr for pts in curves.values() for _, y in pts]
    text, setp = info["temperatura_esterna"], info["set_mandata"]
    active = setp is not None and setp > 0
    if active:
        ys.append(setp)
    if not ys:
        ys = [20, 40]
    ylo = 5 * int((min(ys) - 3) // 5)
    yhi = 5 * int(-(-(max(ys) + 3) // 5))
    if yhi - ylo < 10:
        yhi = ylo + 10

    pw, ph = _W - _ML - _MR, _H - _MT - _MB

    def px(x):
        return _ML + (min(max(x, xmin), xmax) - xmin) / (xmax - xmin) * pw

    def py(y):
        return _MT + (yhi - y) / (yhi - ylo) * ph

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}" '
         f'font-family="Roboto, Helvetica, Arial, sans-serif" font-size="13">']
    # griglia e assi
    for y in range(ylo, yhi + 1, 5):
        s.append(f'<line x1="{_ML}" x2="{_W - _MR}" y1="{py(y):.1f}" y2="{py(y):.1f}" '
                 f'stroke="{_COL["axis"]}" stroke-opacity=".25"/>')
        s.append(f'<text x="{_ML - 8}" y="{py(y) + 4:.1f}" text-anchor="end" fill="{_COL["axis"]}">{y}°</text>')
    for x in range(xmin, xmax + 1, 5):
        s.append(f'<line y1="{_MT}" y2="{_H - _MB}" x1="{px(x):.1f}" x2="{px(x):.1f}" '
                 f'stroke="{_COL["axis"]}" stroke-opacity=".15"/>')
        s.append(f'<text x="{px(x):.1f}" y="{_H - _MB + 18}" text-anchor="middle" '
                 f'fill="{_COL["axis"]}">{x}°</text>')
    s.append(f'<text x="{_ML + pw / 2:.1f}" y="{_H - 6}" text-anchor="middle" fill="{_COL["axis"]}">'
             f'temperatura esterna (°C) — curva {SEASON_LABEL[se]}'
             f'{f", correzione {corr:+.1f}°" if corr else ""}</text>')
    # curve (con correzione), estese piatte ai bordi; economy sotto, comfort sopra.
    # Se coincidono, comfort tratteggiata così si vedono entrambe ed etichette una volta sola.
    same = curves["comfort"] == curves["economy"]
    for lvl in ("economy", "comfort"):
        pts = sorted(curves[lvl])
        if not pts:
            continue
        full = [(xmin, pts[0][1])] + pts + [(xmax, pts[-1][1])]
        path = " ".join(f"{px(x):.1f},{py(y + corr):.1f}" for x, y in full)
        dash = ' stroke-dasharray="10 8"' if same and lvl == "comfort" else ""
        s.append(f'<polyline points="{path}" fill="none" stroke="{_COL[lvl]}" stroke-width="3" '
                 f'stroke-linejoin="round"{dash}/>')
        if same and lvl == "comfort":
            continue
        for x, y in pts:
            s.append(f'<circle cx="{px(x):.1f}" cy="{py(y + corr):.1f}" r="4.5" fill="{_COL[lvl]}"/>')
            above = lvl == "comfort" or same or y >= dict(curves["comfort"]).get(x, y)
            ty = py(y + corr) + (-9 if above else 18)
            s.append(f'<text x="{px(x):.1f}" y="{ty:.1f}" text-anchor="middle" '
                     f'fill="{_COL[lvl]}" font-size="12">{y + corr:.1f}</text>')
    # legenda
    lx = _ML + 10
    if same and curves["comfort"]:
        s.append(f'<text x="{_W - _MR - 10}" y="{_MT + 12}" text-anchor="end" fill="{_COL["axis"]}">'
                 'comfort = economy</text>')
    for lvl in ("comfort", "economy"):
        s.append(f'<rect x="{lx}" y="{_MT + 6}" width="14" height="4" rx="2" fill="{_COL[lvl]}"/>'
                 f'<text x="{lx + 20}" y="{_MT + 12}" fill="{_COL["axis"]}">{LEVEL_LABEL[lvl]}</text>')
        lx += 95
    # punto di lavoro: T esterna attuale → set mandata attuale
    if text is not None:
        x = px(text)
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{_MT}" y2="{_H - _MB}" stroke="{_COL["now"]}" '
                 f'stroke-dasharray="5 4" stroke-width="1.5"/>')
        lbl = f"esterna {text:.1f}°"
        if active:
            s.append(f'<circle cx="{x:.1f}" cy="{py(setp):.1f}" r="7" fill="{_COL["now"]}" '
                     f'stroke="white" stroke-width="2"/>')
            lbl += f" · set {setp:.1f}°"
        else:
            lbl += " · circuito fermo"
        anchor = "start" if x < _ML + pw * 0.6 else "end"
        dx = 8 if anchor == "start" else -8
        s.append(f'<text x="{x + dx:.1f}" y="{_H - _MB - 8}" text-anchor="{anchor}" '
                 f'fill="{_COL["now"]}" font-weight="500">{escape(lbl)}</text>')
    if not any(curves.values()):
        s.append(f'<text x="{_W / 2}" y="{_H / 2}" text-anchor="middle" fill="{_COL["axis"]}">'
                 f'{escape(name)}: curva non disponibile ({escape(str(info["tipo_regolazione"]))})</text>')
    s.append("</svg>")
    return "".join(s).encode()
