import datetime as dt

from app.calc import build_year, default_month, get_week
from app.tax import bruto_netto


def put(conn, date, hours, storing=0, vakantie=0, factor=1):
    conn.execute("INSERT OR REPLACE INTO days(date, hours, storing, vakantie, factor, updated_at) "
                 "VALUES(?,?,?,?,?, '2026-01-01T00:00:00')", (date, hours, storing, vakantie, factor))


def test_week_totaal_en_overuren(conn):
    # week 44 van 2026: ma 26-10 t/m zo 1-11
    for i, h in enumerate([10, 10, 10, 10, 8, 4]):
        put(conn, (dt.date(2026, 10, 26) + dt.timedelta(days=i)).isoformat(), h)
    w = get_week(conn, 2026, 44)
    assert w.total == 52
    assert w.overuren == 12
    assert w.month == 10  # donderdag 29-10


def test_zondag_dubbel_telt_dubbel_in_weektotaal(conn):
    for i in range(5):
        put(conn, (dt.date(2026, 10, 26) + dt.timedelta(days=i)).isoformat(), 8)
    put(conn, "2026-11-01", 4, factor=2)       # zondag 2x
    put(conn, "2026-10-31", 2, factor=1.5)     # zaterdag 1,5x
    w = get_week(conn, 2026, 44)
    assert w.gewerkt == 46
    assert w.total == 40 + 3 + 8
    assert w.overuren == 11


def test_maand_bedragen(conn):
    conn.execute("INSERT INTO years(year, contract_hours, rate1, rate2, storing_rate, vakantie_totaal) "
                 "VALUES(2026, 40, 16.15, 17, 10, 21)")
    for i in range(5):
        put(conn, (dt.date(2026, 10, 5) + dt.timedelta(days=i)).isoformat(), 10, storing=1 if i < 2 else 0)
    put(conn, "2026-10-12", 8, vakantie=1)
    conn.execute("INSERT INTO months(year, month, bruto, netto, schaal) VALUES(2026, 10, 3700, 2800, 1)")
    Y = build_year(conn, 2026)
    m = Y["months"][9]
    assert m.overuren == 10
    assert m.overuren_euro == 161.5
    assert m.storing_euro == 20
    assert m.totaal_netto == 2800 + 161.5 + 20
    assert Y["totals"]["vakantie_over"] == 20
    assert Y["totals"]["vakantie_uitbetalen"] == round(20 * 16.15 * 8, 2)


def test_schaal_2(conn):
    conn.execute("INSERT INTO years(year, rate1, rate2) VALUES(2026, 15, 17)")
    for i in range(5):
        put(conn, (dt.date(2026, 3, 2) + dt.timedelta(days=i)).isoformat(), 9)
    conn.execute("INSERT INTO months(year, month, schaal) VALUES(2026, 3, 2)")
    assert build_year(conn, 2026)["months"][2].overuren_euro == 5 * 17


def test_maand_override(conn):
    conn.execute("INSERT INTO weeks(iso_year, week, month) VALUES(2026, 40, 9)")
    assert default_month(2026, 40) == 10
    assert get_week(conn, 2026, 40).month == 9


def test_bruto_netto_redelijk():
    r = bruto_netto(3700, 2026)
    assert 2900 < r["netto"] < 3100
    assert r["loonbelasting"] > r["algemene_heffingskorting"] + r["arbeidskorting"]
    zonder = bruto_netto(3700, 2026, loonheffingskorting=False)
    assert zonder["netto"] < r["netto"]
    assert bruto_netto(0, 2026)["netto"] == 0


def test_feestdagen():
    from app.holidays import easter, holiday_dates
    d = holiday_dates(2026)
    assert easter(2026) == dt.date(2026, 4, 5) and easter(2025) == dt.date(2025, 4, 20)
    assert d["koningsdag"] == dt.date(2026, 4, 27)
    assert d["hemelvaart"] == dt.date(2026, 5, 14)
    assert (d["pinksteren1"], d["pinksteren2"]) == (dt.date(2026, 5, 24), dt.date(2026, 5, 25))
    assert holiday_dates(2025)["koningsdag"] == dt.date(2025, 4, 26)  # 27-4-2025 is zondag


def test_standaardfactor_en_naam(conn):
    from app import holidays
    w = get_week(conn, 2026, 15)  # 6-4 t/m 12-4: 2e Paasdag op maandag
    assert w.holiday[0] == "2e Paasdag" and w.default_factor[0] == 2.0
    assert w.default_factor[6] == 2.0  # zondag
    assert w.default_factor[2] == 1.0
    s = holidays.get_settings()
    s["days"]["pasen2"]["factor"] = 1.5
    holidays.save_settings(1.0, s["days"])
    w = get_week(conn, 2026, 15)
    assert w.default_factor[0] == 1.5 and w.default_factor[6] == 1.0


def test_ontbrekende_dagen(conn):
    # eerste ingevulde dag: ma 5-1-2025; di leeg, wo vakantie, do leeg, vr ingevuld
    put(conn, "2025-01-06", 8)
    put(conn, "2025-01-08", None, vakantie=1)
    put(conn, "2025-01-10", 8)
    Y = build_year(conn, 2025)
    missing = [d.isoformat() for _, d in Y["missing"]]
    assert "2025-01-07" in missing and "2025-01-09" in missing
    assert "2025-01-08" not in missing and "2025-01-11" not in missing  # vakantie / zaterdag
    assert "2025-04-21" not in missing  # 2e Paasdag
    assert "2025-01-01" not in missing  # voor de eerste ingevulde dag
