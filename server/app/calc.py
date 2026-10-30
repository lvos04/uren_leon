"""Rekenregels, overgenomen uit het Excel-bestand.

- Een week loopt van maandag t/m zondag (ISO-week).
- Overuren per week = weektotaal - contracturen (nooit negatief).
- Een week hoort bij de maand waarin de donderdag valt, tenzij handmatig anders ingesteld.
- Overuren worden netto uitbetaald: uren x tarief (schaal 1 of 2). Geen belasting.
- Een dag kan 1,5x of 2x tellen (zon-/feestdag): de uren van die dag tellen dan 1,5x of 2x mee
  in het weektotaal (8 uur op 2x = 16 uur). Overuren = dat weektotaal - contracturen.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
           "augustus", "september", "oktober", "november", "december"]
DAGEN = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
DAGEN_KORT = ["ma", "di", "wo", "do", "vr", "za", "zo"]

DEFAULT_SETTINGS = dict(contract_hours=40.0, rate1=15.0, rate2=17.0, storing_rate=10.0,
                        vakantie_totaal=21.0, loonheffingskorting=1, situatie="standard")


def weeks_in_year(year: int) -> int:
    return dt.date(year, 12, 28).isocalendar()[1]


def week_dates(iso_year: int, week: int) -> list[dt.date]:
    return [dt.date.fromisocalendar(iso_year, week, d) for d in range(1, 8)]


def default_month(iso_year: int, week: int) -> int:
    return dt.date.fromisocalendar(iso_year, week, 4).month


def get_settings(conn, year: int) -> dict:
    row = conn.execute("SELECT * FROM years WHERE year<=? ORDER BY year DESC LIMIT 1", (year,)).fetchone()
    if row is None:
        row = conn.execute("SELECT * FROM years ORDER BY year LIMIT 1").fetchone()
    s = dict(DEFAULT_SETTINGS)
    if row is not None:
        s.update({k: row[k] for k in DEFAULT_SETTINGS})
    s["year"] = year
    s["own"] = conn.execute("SELECT 1 FROM years WHERE year=?", (year,)).fetchone() is not None
    return s


@dataclass
class Week:
    iso_year: int
    week: int
    month: int
    month_override: bool
    dates: list
    hours: list            # per dag, None = niet ingevuld
    storing: list          # per dag bool
    vakantie: list         # per dag float
    factor: list = field(default_factory=lambda: [1.0] * 7)  # per dag 1 / 1.5 / 2
    storing_extra: int = 0
    vakantie_extra: float = 0.0
    contract: float = 40.0

    @property
    def total(self) -> float:
        """Weektotaal, met zon-/feestdagen 1,5x of 2x meegeteld."""
        return sum((h or 0) * f for h, f in zip(self.hours, self.factor))

    @property
    def gewerkt(self) -> float:
        """Werkelijk gewerkte uren (zonder factor)."""
        return sum(h or 0 for h in self.hours)

    @property
    def has_data(self) -> bool:
        return any(h is not None for h in self.hours) or self.storing_days or self.vakantie_days

    @property
    def overuren(self) -> float:
        return max(0.0, self.total - self.contract) if self.total else 0.0

    @property
    def storing_days(self) -> int:
        return sum(1 for s in self.storing if s) + self.storing_extra

    @property
    def vakantie_days(self) -> float:
        return sum(self.vakantie) + self.vakantie_extra


@dataclass
class Month:
    year: int
    month: int
    weeks: list = field(default_factory=list)
    bruto: float | None = None
    netto: float | None = None
    schaal: int = 1
    rate: float = 0.0
    storing_rate: float = 0.0

    @property
    def naam(self) -> str:
        return MAANDEN[self.month - 1]

    @property
    def uren(self) -> float:
        return sum(w.total for w in self.weeks)

    @property
    def overuren(self) -> float:
        return sum(w.overuren for w in self.weeks)

    @property
    def gewerkt(self) -> float:
        return sum(w.gewerkt for w in self.weeks)

    @property
    def overuren_euro(self) -> float:
        return round(self.overuren * self.rate, 2)

    @property
    def storing_days(self) -> int:
        return sum(w.storing_days for w in self.weeks)

    @property
    def storing_euro(self) -> float:
        return round(self.storing_days * self.storing_rate, 2)

    @property
    def vakantie_days(self) -> float:
        return sum(w.vakantie_days for w in self.weeks)

    @property
    def totaal_netto(self) -> float:
        return round((self.netto or 0) + self.overuren_euro + self.storing_euro, 2)


def load_days(conn, start: dt.date, end: dt.date) -> dict:
    rows = conn.execute("SELECT * FROM days WHERE date BETWEEN ? AND ?",
                        (start.isoformat(), end.isoformat())).fetchall()
    return {r["date"]: r for r in rows}


def build_weeks(conn, iso_year: int, settings: dict | None = None) -> list[Week]:
    settings = settings or get_settings(conn, iso_year)
    n = weeks_in_year(iso_year)
    start = dt.date.fromisocalendar(iso_year, 1, 1)
    end = dt.date.fromisocalendar(iso_year, n, 7)
    days = load_days(conn, start, end)
    meta = {r["week"]: r for r in conn.execute("SELECT * FROM weeks WHERE iso_year=?", (iso_year,))}
    out = []
    for w in range(1, n + 1):
        dates = week_dates(iso_year, w)
        rows = [days.get(d.isoformat()) for d in dates]
        m = meta.get(w)
        override = m["month"] if m is not None and m["month"] else None
        out.append(Week(
            iso_year=iso_year, week=w,
            month=override or default_month(iso_year, w), month_override=bool(override),
            dates=dates,
            hours=[r["hours"] if r is not None else None for r in rows],
            storing=[bool(r["storing"]) if r is not None else False for r in rows],
            vakantie=[(r["vakantie"] or 0) if r is not None else 0 for r in rows],
            factor=[(r["factor"] or 1) if r is not None else 1.0 for r in rows],
            storing_extra=m["storing_extra"] if m is not None else 0,
            vakantie_extra=m["vakantie_extra"] if m is not None else 0,
            contract=settings["contract_hours"],
        ))
    return out


def get_week(conn, iso_year: int, week: int) -> Week:
    return build_weeks(conn, iso_year)[week - 1]


def build_year(conn, year: int) -> dict:
    s = get_settings(conn, year)
    weeks = build_weeks(conn, year, s)
    mrows = {r["month"]: r for r in conn.execute("SELECT * FROM months WHERE year=?", (year,))}
    months = []
    for m in range(1, 13):
        r = mrows.get(m)
        schaal = r["schaal"] if r is not None else 1
        months.append(Month(
            year=year, month=m, weeks=[w for w in weeks if w.month == m],
            bruto=r["bruto"] if r is not None else None,
            netto=r["netto"] if r is not None else None,
            schaal=schaal, rate=s["rate1"] if schaal == 1 else s["rate2"],
            storing_rate=s["storing_rate"],
        ))
    payouts = [dict(r) for r in conn.execute(
        "SELECT * FROM payouts WHERE substr(date,1,4)=? ORDER BY date", (str(year),))]

    worked = [w for w in weeks if w.total > 0]
    over40 = [w.total for w in weeks if w.total > s["contract_hours"]]
    with_ot = [w.overuren for w in weeks if w.overuren > 0]
    vak_used = sum(w.vakantie_days for w in weeks)
    vak_left = s["vakantie_totaal"] - vak_used
    bruto_netto = [(mo.bruto, mo.netto) for mo in months if mo.bruto and mo.netto]
    ot_euro = sum(mo.overuren_euro for mo in months)
    storing_euro = sum(mo.storing_euro for mo in months)
    paid = sum(p["amount"] for p in payouts)
    totals = dict(
        uren=sum(w.total for w in weeks),
        overuren=sum(w.overuren for w in weeks),
        weken_gewerkt=len(worked),
        gem_week_boven_contract=(sum(over40) / len(over40)) if over40 else 0,
        gem_overuren=(sum(with_ot) / len(with_ot)) if with_ot else 0,
        overuren_euro=round(ot_euro, 2),
        storing_dagen=sum(mo.storing_days for mo in months),
        storing_euro=round(storing_euro, 2),
        bruto=round(sum(mo.bruto or 0 for mo in months), 2),
        netto=round(sum(mo.netto or 0 for mo in months), 2),
        totaal_netto=round(sum(mo.totaal_netto for mo in months), 2),
        belasting_betaald=round(sum(b - n for b, n in bruto_netto), 2),
        vakantie_gebruikt=vak_used,
        vakantie_over=vak_left,
        vakantie_uitbetalen=round(vak_left * s["rate1"] * 8, 2),
        uitbetaald=round(paid, 2),
        nog_te_goed=round(ot_euro + storing_euro - paid, 2) if payouts else None,
    )
    return dict(year=year, settings=s, weeks=weeks, months=months, payouts=payouts, totals=totals)


def fmt_hours(v) -> str:
    if v is None:
        return ""
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.2f}".rstrip("0").replace(".", ",")


def fmt_euro(v) -> str:
    if v is None:
        return ""
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-€ " if v < 0 else "€ ") + s
