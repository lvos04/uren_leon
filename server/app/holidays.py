"""Nederlandse feestdagen en hoe zwaar ze (en zondag) standaard meetellen.

De factor is alleen een voorinstelling bij het invullen: wat bij een dag is opgeslagen telt.
"""
from __future__ import annotations

import datetime as dt
import json

from . import db

# key, naam, standaard aan
HOLIDAYS = [
    ("nieuwjaar", "Nieuwjaarsdag", True),
    ("goedevrijdag", "Goede Vrijdag", False),
    ("pasen1", "1e Paasdag", True),
    ("pasen2", "2e Paasdag", True),
    ("koningsdag", "Koningsdag", True),
    ("bevrijdingsdag", "Bevrijdingsdag", False),
    ("hemelvaart", "Hemelvaartsdag", True),
    ("pinksteren1", "1e Pinksterdag", True),
    ("pinksteren2", "2e Pinksterdag", True),
    ("kerst1", "1e Kerstdag", True),
    ("kerst2", "2e Kerstdag", True),
]
NAMES = {k: n for k, n, _ in HOLIDAYS}


def easter(year: int) -> dt.date:
    """Paaszondag (anonieme Gregoriaanse berekening, Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def holiday_dates(year: int) -> dict[str, dt.date]:
    e = easter(year)
    koning = dt.date(year, 4, 27)
    if koning.weekday() == 6:
        koning = dt.date(year, 4, 26)
    return {
        "nieuwjaar": dt.date(year, 1, 1),
        "goedevrijdag": e - dt.timedelta(days=2),
        "pasen1": e,
        "pasen2": e + dt.timedelta(days=1),
        "koningsdag": koning,
        "bevrijdingsdag": dt.date(year, 5, 5),
        "hemelvaart": e + dt.timedelta(days=39),
        "pinksteren1": e + dt.timedelta(days=49),
        "pinksteren2": e + dt.timedelta(days=50),
        "kerst1": dt.date(year, 12, 25),
        "kerst2": dt.date(year, 12, 26),
    }


DEFAULT_SETTINGS = {
    "sunday_factor": 2.0,
    "days": {k: {"on": on, "factor": 2.0} for k, _, on in HOLIDAYS},
}


def get_settings(conn=None) -> dict:
    def load(c):
        raw = db.get_meta(c, "holiday_settings")
        s = json.loads(json.dumps(DEFAULT_SETTINGS))
        if raw:
            stored = json.loads(raw)
            s["sunday_factor"] = float(stored.get("sunday_factor", s["sunday_factor"]))
            for k, v in stored.get("days", {}).items():
                if k in s["days"]:
                    s["days"][k].update(on=bool(v.get("on")), factor=float(v.get("factor", 2)))
        return s
    if conn is not None:
        return load(conn)
    with db.get_conn() as c:
        return load(c)


def save_settings(sunday_factor: float, days: dict) -> None:
    with db.get_conn() as c:
        db.set_meta(c, "holiday_settings", json.dumps({"sunday_factor": sunday_factor, "days": days}))


def holidays_between(start: dt.date, end: dt.date, settings: dict | None = None) -> dict[dt.date, dict]:
    """Alle ingeschakelde feestdagen tussen start en end: {datum: {name, factor}}."""
    s = settings or get_settings()
    out = {}
    for year in range(start.year, end.year + 1):
        for key, d in holiday_dates(year).items():
            cfg = s["days"][key]
            if cfg["on"] and start <= d <= end:
                out[d] = {"key": key, "name": NAMES[key], "factor": cfg["factor"]}
    return out


def default_factor(d: dt.date, settings: dict | None = None, hol: dict | None = None) -> float:
    s = settings or get_settings()
    hol = hol if hol is not None else holidays_between(d, d, s)
    if d in hol:
        return hol[d]["factor"]
    if d.weekday() == 6:
        return s["sunday_factor"]
    return 1.0
