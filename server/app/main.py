"""Uren & salaris - web-app + API."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import auth, backup, db, onedrive, printing
from .calc import (DAGEN, DAGEN_KORT, MAANDEN, build_year, fmt_euro, fmt_hours, get_settings, get_week,
                   weeks_in_year)
from .export_xlsx import export_workbook
from .importer import import_into, parse_workbook
from .tax import SITUATIES, bruto_netto

logging.basicConfig(level=logging.INFO)
BASE = Path(__file__).parent

db.init_db()


SCHED = {"s": None}


def _start_scheduler():
    """Dagelijkse backup op de tijd uit Instellingen."""
    from apscheduler.schedulers.background import BackgroundScheduler
    sched = BackgroundScheduler(timezone=os.environ.get("TZ", "Europe/Amsterdam"))
    sched.start()
    SCHED["s"] = sched
    plan_backup()
    return sched


def plan_backup():
    sched = SCHED["s"]
    if sched is None:
        return
    from apscheduler.triggers.cron import CronTrigger
    hh, mm = backup.get_settings()["backup_time"].split(":")
    sched.add_job(backup.run_backup, CronTrigger(hour=int(hh), minute=int(mm)), id="backup",
                  misfire_grace_time=6 * 3600, coalesce=True, replace_existing=True)


@asynccontextmanager
async def lifespan(_app):
    sched = None if os.environ.get("DISABLE_SCHEDULER") == "1" else _start_scheduler()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="Uren", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=db.session_secret(), session_cookie="uren_sessie",
                   max_age=60 * 60 * 24 * 90, same_site="lax",
                   https_only=os.environ.get("SESSION_HTTPS_ONLY", "0") == "1")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters["uur"] = fmt_hours
templates.env.filters["euro"] = fmt_euro
templates.env.globals.update(MAANDEN=MAANDEN, DAGEN=DAGEN, DAGEN_KORT=DAGEN_KORT)


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def page(request: Request, name: str, **ctx):
    ctx.setdefault("today", dt.date.today())
    return templates.TemplateResponse(request, name, ctx)


def parse_num(v: str | None) -> float | None:
    if v is None:
        return None
    v = v.strip().replace(",", ".")
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        raise HTTPException(400, f"Ongeldig getal: {v}")


@app.exception_handler(auth.NeedLogin)
async def _need_login(request: Request, exc):
    return RedirectResponse("/login?next=" + quote(request.url.path), status_code=303)


@app.exception_handler(auth.NeedSetup)
async def _need_setup(request: Request, exc):
    return RedirectResponse("/setup", status_code=303)


# ---------------------------------------------------------------- eerste keer
@app.get("/setup", response_class=HTMLResponse)
def setup_form(request: Request):
    if auth.password_is_set():
        return RedirectResponse("/login", status_code=303)
    return page(request, "setup.html", error=None, allowed=auth.is_private_client(request))


@app.post("/setup")
def setup(request: Request, password: str = Form(...), password2: str = Form(...), naam: str = Form("")):
    if auth.password_is_set():
        return RedirectResponse("/login", status_code=303)
    if not auth.is_private_client(request):
        raise HTTPException(403, "Stel het wachtwoord in vanaf je thuisnetwerk")
    error = None
    if len(password) < 8:
        error = "Kies een wachtwoord van minstens 8 tekens"
    elif password != password2:
        error = "De twee wachtwoorden zijn niet gelijk"
    if error:
        return page(request, "setup.html", error=error, allowed=True)
    auth.set_password(password)
    with db.get_conn() as conn:
        if naam.strip():
            db.set_meta(conn, "naam", naam.strip())
    request.session["ok"] = True
    return RedirectResponse("/instellingen?msg=" + quote("Welkom! Importeer hieronder je oude Excel-bestand."),
                            status_code=303)


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ---------------------------------------------------------------- login
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/"):
    if not auth.password_is_set():
        return RedirectResponse("/setup", status_code=303)
    return page(request, "login.html", next=next, error=None)


@app.post("/login")
def login(request: Request, password: str = Form(...), next: str = Form("/")):
    if not auth.check_password(password):
        return page(request, "login.html", next=next, error="Wachtwoord klopt niet")
    request.session["ok"] = True
    return RedirectResponse(next if next.startswith("/") and not next.startswith("//") else "/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------------------------------------------------------------- pagina's
@app.get("/", dependencies=[Depends(auth.require_web)])
def home():
    return RedirectResponse(f"/jaar/{dt.date.today().isocalendar()[0]}", status_code=303)


@app.get("/vandaag", dependencies=[Depends(auth.require_web)])
def vandaag():
    y, w, _ = dt.date.today().isocalendar()
    return RedirectResponse(f"/week/{y}/{w}", status_code=303)


@app.get("/jaar/{year}", response_class=HTMLResponse, dependencies=[Depends(auth.require_web)])
def jaar(request: Request, year: int):
    with db.get_conn() as conn:
        Y = build_year(conn, year)
    cur = dt.date.today().isocalendar()
    return page(request, "jaar.html", Y=Y, cur_week=cur[1] if cur[0] == year else None)


@app.get("/week/{year}/{week}", response_class=HTMLResponse, dependencies=[Depends(auth.require_web)])
def week_form(request: Request, year: int, week: int, saved: int = 0):
    if not 1 <= week <= weeks_in_year(year):
        raise HTTPException(404)
    with db.get_conn() as conn:
        W = get_week(conn, year, week)
        notes = {r["date"]: r["note"] for r in conn.execute(
            "SELECT date, note FROM days WHERE date BETWEEN ? AND ?",
            (W.dates[0].isoformat(), W.dates[-1].isoformat()))}
    prev = (W.dates[0] - dt.timedelta(days=7)).isocalendar()
    nxt = (W.dates[0] + dt.timedelta(days=7)).isocalendar()
    return page(request, "week.html", W=W, notes=notes, saved=saved,
                prev=(prev[0], prev[1]), next=(nxt[0], nxt[1]))


@app.post("/week/{year}/{week}", dependencies=[Depends(auth.require_web)])
async def week_save(request: Request, year: int, week: int):
    form = await request.form()
    with db.get_conn() as conn:
        W = get_week(conn, year, week)
        for i, d in enumerate(W.dates):
            hours = parse_num(form.get(f"h{i}"))
            storing = 1 if form.get(f"s{i}") else 0
            vak = parse_num(form.get(f"v{i}")) or 0
            factor = parse_num(form.get(f"f{i}")) or 1
            note = (form.get(f"n{i}") or "").strip() or None
            if hours is None and not storing and not vak and not note and factor == 1:
                conn.execute("DELETE FROM days WHERE date=?", (d.isoformat(),))
            else:
                upsert_day(conn, d.isoformat(), hours, storing, vak, note, now_iso(), factor)
        month = int(form.get("month") or 0) or None
        s_extra = int(parse_num(form.get("storing_extra")) or 0)
        v_extra = parse_num(form.get("vakantie_extra")) or 0
        conn.execute("INSERT OR REPLACE INTO weeks(iso_year, week, month, storing_extra, vakantie_extra) "
                     "VALUES(?,?,?,?,?)", (year, week, month, s_extra, v_extra))
    return RedirectResponse(f"/week/{year}/{week}?saved=1", status_code=303)


@app.get("/maand/{year}/{month}", response_class=HTMLResponse, dependencies=[Depends(auth.require_web)])
def maand(request: Request, year: int, month: int, saved: int = 0):
    if not 1 <= month <= 12:
        raise HTTPException(404)
    with db.get_conn() as conn:
        Y = build_year(conn, year)
    M = Y["months"][month - 1]
    schatting = bruto_netto(M.bruto, year, bool(Y["settings"]["loonheffingskorting"]),
                            Y["settings"]["situatie"]) if M.bruto else None
    return page(request, "maand.html", Y=Y, M=M, saved=saved, schatting=schatting)


@app.post("/maand/{year}/{month}", dependencies=[Depends(auth.require_web)])
def maand_save(year: int, month: int, bruto: str = Form(""), netto: str = Form(""), schaal: int = Form(1)):
    with db.get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO months(year, month, bruto, netto, schaal) VALUES(?,?,?,?,?)",
                     (year, month, parse_num(bruto), parse_num(netto), 2 if schaal == 2 else 1))
    return RedirectResponse(f"/maand/{year}/{month}?saved=1", status_code=303)


# ---------------------------------------------------------------- printen
def _pdf(year: int, months: list[int], name: str) -> Response:
    with db.get_conn() as conn:
        data = printing.render_pdf(conn, year, months)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


@app.get("/print/{year}/{month}.pdf", dependencies=[Depends(auth.require_web)])
def print_pdf(year: int, month: int):
    return _pdf(year, [month], f"uren-{year}-{month:02d}.pdf")


@app.get("/print/{year}.pdf", dependencies=[Depends(auth.require_web)])
def print_year_pdf(year: int):
    return _pdf(year, list(range(1, 13)), f"uren-{year}.pdf")


@app.get("/print/{year}/{month}", response_class=HTMLResponse, dependencies=[Depends(auth.require_web)])
def print_html(year: int, month: int):
    with db.get_conn() as conn:
        return HTMLResponse(printing.render_html(conn, year, [month]))


# ---------------------------------------------------------------- calculator
@app.get("/calculator", response_class=HTMLResponse, dependencies=[Depends(auth.require_web)])
def calculator(request: Request, bruto: str = "", jaar: int | None = None, lhk: str = "ja",
               situatie: str = "standard", pensioen: str = "", overig: str = ""):
    year = jaar or dt.date.today().year
    res = None
    b = parse_num(bruto)
    if b:
        res = bruto_netto(b, year, lhk == "ja", situatie, parse_num(pensioen) or 0, parse_num(overig) or 0)
    return page(request, "calculator.html", res=res, bruto=bruto, jaar=year, lhk=lhk, situatie=situatie,
                pensioen=pensioen, overig=overig, SITUATIES=SITUATIES)


@app.post("/calculator/overnemen", dependencies=[Depends(auth.require_web)])
def calculator_take(jaar: int = Form(...), maand: int = Form(...), bruto: str = Form(...), netto: str = Form(...)):
    with db.get_conn() as conn:
        row = conn.execute("SELECT schaal FROM months WHERE year=? AND month=?", (jaar, maand)).fetchone()
        conn.execute("INSERT OR REPLACE INTO months(year, month, bruto, netto, schaal) VALUES(?,?,?,?,?)",
                     (jaar, maand, parse_num(bruto), parse_num(netto), row["schaal"] if row else 1))
    return RedirectResponse(f"/maand/{jaar}/{maand}?saved=1", status_code=303)


# ---------------------------------------------------------------- instellingen
APK_DIR = Path(os.environ.get("APK_DIR", "/srv/apk"))


def app_info() -> dict | None:
    f = APK_DIR / "version.json"
    if not f.exists() or not (APK_DIR / "uren.apk").exists():
        return None
    import json
    return json.loads(f.read_text())


def public_url(request: Request) -> str:
    with db.get_conn() as conn:
        u = db.get_meta(conn, "public_url", "")
    return u or str(request.base_url).rstrip("/")


def back(msg: str, anchor: str = "") -> RedirectResponse:
    return RedirectResponse("/instellingen?msg=" + quote(msg) + (f"#{anchor}" if anchor else ""), status_code=303)


@app.get("/instellingen", response_class=HTMLResponse, dependencies=[Depends(auth.require_web)])
def instellingen(request: Request, jaar: int | None = None, msg: str = ""):
    year = jaar or dt.date.today().year
    with db.get_conn() as conn:
        s = get_settings(conn, year)
        tokens = conn.execute("SELECT id, name, created_at FROM tokens ORDER BY id").fetchall()
        payouts = conn.execute("SELECT * FROM payouts ORDER BY date DESC").fetchall()
        naam = db.get_meta(conn, "naam", "")
        purl = db.get_meta(conn, "public_url", "")
    return page(request, "instellingen.html", s=s, jaar=year, tokens=tokens, payouts=payouts, naam=naam,
                msg=msg, backup=backup.last_status(), bset=backup.get_settings(), backups=backup.list_backups(),
                linked=backup.onedrive_linked(), SITUATIES=SITUATIES, app=app_info(),
                public_url=purl, guessed_url=str(request.base_url).rstrip("/"))


@app.post("/instellingen/jaar", dependencies=[Depends(auth.require_web)])
def instellingen_jaar(jaar: int = Form(...), contract_hours: str = Form(...), rate1: str = Form(...),
                      rate2: str = Form(...), storing_rate: str = Form(...), vakantie_totaal: str = Form(...),
                      loonheffingskorting: str = Form("ja"), situatie: str = Form("standard")):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO years(year, contract_hours, rate1, rate2, storing_rate, vakantie_totaal, "
            "loonheffingskorting, situatie) VALUES(?,?,?,?,?,?,?,?)",
            (jaar, parse_num(contract_hours), parse_num(rate1), parse_num(rate2), parse_num(storing_rate),
             parse_num(vakantie_totaal), 1 if loonheffingskorting == "ja" else 0,
             situatie if situatie in SITUATIES else "standard"))
    return RedirectResponse(f"/instellingen?jaar={jaar}&msg=Instellingen+{jaar}+opgeslagen", status_code=303)


@app.post("/instellingen/account", dependencies=[Depends(auth.require_web)])
def instellingen_account(naam: str = Form(""), public_url_in: str = Form("", alias="public_url")):
    u = public_url_in.strip().rstrip("/")
    if u and not u.startswith(("http://", "https://")):
        u = "https://" + u
    with db.get_conn() as conn:
        db.set_meta(conn, "naam", naam.strip())
        db.set_meta(conn, "public_url", u)
    return back("Opgeslagen", "account")


@app.post("/instellingen/wachtwoord", dependencies=[Depends(auth.require_web)])
def instellingen_wachtwoord(oud: str = Form(...), nieuw: str = Form(...), nieuw2: str = Form(...)):
    if not auth.check_password(oud):
        return back("Huidig wachtwoord klopt niet", "account")
    if len(nieuw) < 8 or nieuw != nieuw2:
        return back("Nieuw wachtwoord: minstens 8 tekens en twee keer hetzelfde", "account")
    auth.set_password(nieuw)
    return back("Wachtwoord gewijzigd", "account")


# ---- telefoon koppelen
@app.post("/koppel", response_class=HTMLResponse, dependencies=[Depends(auth.require_web)])
def koppel(request: Request, name: str = Form("Telefoon")):
    import io

    import qrcode
    import qrcode.image.svg
    token = auth.create_token(name.strip() or "Telefoon")
    url = public_url(request)
    link = "uren://koppel?" + urlencode({"url": url, "token": token})
    buf = io.BytesIO()
    qrcode.make(link, image_factory=qrcode.image.svg.SvgPathImage, box_size=12).save(buf)
    return page(request, "koppel.html", link=link, qr=buf.getvalue().decode(), url=url, token=token, app=app_info())


@app.post("/tokens/{tid}/delete", dependencies=[Depends(auth.require_web)])
def token_delete(tid: int):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM tokens WHERE id=?", (tid,))
    return back("Telefoon ontkoppeld", "telefoon")


@app.get("/app/uren.apk", dependencies=[Depends(auth.require_web)])
def apk_download():
    return _apk_response()


def _apk_response():
    f = APK_DIR / "uren.apk"
    if not f.exists():
        raise HTTPException(404, "Geen app meegeleverd in deze versie")
    return FileResponse(f, media_type="application/vnd.android.package-archive", filename="uren.apk")


# ---- backup
@app.post("/instellingen/backup", dependencies=[Depends(auth.require_web)])
def instellingen_backup(tijd: str = Form(...), map_: str = Form("UrenBackup", alias="map"), dagen: int = Form(30)):
    try:
        backup.save_settings(tijd, map_, dagen)
    except ValueError as e:
        return back(str(e), "backup")
    plan_backup()
    return back("Backup-instellingen opgeslagen", "backup")


@app.post("/backup", dependencies=[Depends(auth.require_web)])
def backup_now():
    r = backup.run_backup()
    if r["ok"] and r["upload"] == "ok":
        msg = "Backup gemaakt en naar OneDrive gezet"
    elif r["ok"]:
        msg = "Backup gemaakt (alleen op de server: OneDrive is niet gekoppeld)"
    else:
        msg = f"Backup mislukt: {r['error']}"
    return back(msg, "backup")


@app.get("/backups/{name}", dependencies=[Depends(auth.require_web)])
def backup_download(name: str):
    try:
        f = backup.backup_file(name)
    except FileNotFoundError:
        raise HTTPException(404)
    return FileResponse(f, filename=name)


@app.post("/backups/{name}/restore", dependencies=[Depends(auth.require_web)])
def backup_restore(name: str):
    try:
        safety = backup.restore(name)
    except Exception as e:  # noqa: BLE001
        return back(f"Terugzetten mislukt: {e}", "backup")
    return back(f"{name} teruggezet. De gegevens van vóór het terugzetten staan in {safety}.", "backup")


# ---- OneDrive
@app.get("/onedrive", response_class=HTMLResponse, dependencies=[Depends(auth.require_web)])
def onedrive_page(request: Request):
    return page(request, "onedrive.html", login_url=None, error=None, linked=backup.onedrive_linked(),
                folder=backup.get_settings()["backup_folder"])


@app.post("/onedrive/start", response_class=HTMLResponse, dependencies=[Depends(auth.require_web)])
def onedrive_start(request: Request):
    try:
        url = onedrive.start()
        err = None
    except Exception as e:  # noqa: BLE001
        url, err = None, str(e)
    return page(request, "onedrive.html", login_url=url, error=err, linked=backup.onedrive_linked(),
                folder=backup.get_settings()["backup_folder"])


@app.post("/onedrive/finish", response_class=HTMLResponse, dependencies=[Depends(auth.require_web)])
def onedrive_finish(request: Request, adres: str = Form(...)):
    try:
        drive = onedrive.finish(adres)
    except Exception as e:  # noqa: BLE001
        return page(request, "onedrive.html", login_url=None, error=str(e), linked=backup.onedrive_linked(),
                folder=backup.get_settings()["backup_folder"])
    who = (drive.get("owner") or {}).get("user", {}).get("displayName", "")
    return back(f"OneDrive gekoppeld{(' (' + who + ')') if who else ''}. Klik op 'Nu backup maken' om te testen.",
                "backup")


@app.post("/onedrive/test", dependencies=[Depends(auth.require_web)])
def onedrive_test():
    return back(onedrive.test(), "backup")


@app.post("/onedrive/unlink", dependencies=[Depends(auth.require_web)])
def onedrive_unlink():
    onedrive.unlink()
    return back("OneDrive ontkoppeld", "backup")


@app.post("/import", dependencies=[Depends(auth.require_web)])
async def import_xlsx(file: UploadFile = File(...)):
    data = await file.read()
    try:
        parsed = parse_workbook(data)
    except Exception as e:  # noqa: BLE001
        return RedirectResponse("/instellingen?msg=" + quote(f"Import mislukt: {e}"), status_code=303)
    with db.get_conn() as conn:
        stats = import_into(conn, parsed, now=now_iso())
    msg = "Geïmporteerd: " + ", ".join(f"{y} ({s['dagen']} dagen)" for y, s in stats.items())
    return RedirectResponse("/instellingen?msg=" + quote(msg), status_code=303)


@app.get("/export.xlsx", dependencies=[Depends(auth.require_web)])
def export():
    with db.get_conn() as conn:
        data = export_workbook(conn)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="uren-{dt.date.today()}.xlsx"'})


@app.post("/uitbetalingen", dependencies=[Depends(auth.require_web)])
def payout_add(date: str = Form(...), amount: str = Form(...), note: str = Form("")):
    dt.date.fromisoformat(date)
    with db.get_conn() as conn:
        conn.execute("INSERT INTO payouts(date, amount, note) VALUES(?,?,?)",
                     (date, parse_num(amount), note.strip() or None))
    return RedirectResponse("/instellingen?msg=Uitbetaling+toegevoegd#uitbetalingen", status_code=303)


@app.post("/uitbetalingen/{pid}/delete", dependencies=[Depends(auth.require_web)])
def payout_delete(pid: int):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM payouts WHERE id=?", (pid,))
    return RedirectResponse("/instellingen?msg=Uitbetaling+verwijderd#uitbetalingen", status_code=303)


# ---------------------------------------------------------------- API (Android)
api = "/api/v1"


class DayIn(BaseModel):
    hours: float | None = Field(default=None, ge=0, le=24)
    storing: bool = False
    vakantie: float = Field(default=0, ge=0, le=1)
    factor: float = Field(default=1, ge=1, le=3)  # 1, 1.5 of 2 voor zon-/feestdagen
    note: str | None = None
    updated_at: str | None = None  # ISO tijd van de wijziging op de telefoon


def upsert_day(conn, date: str, hours, storing, vakantie, note, updated_at, factor=1.0):
    conn.execute(
        "INSERT INTO days(date, hours, storing, vakantie, factor, note, updated_at) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(date) DO UPDATE SET hours=excluded.hours, storing=excluded.storing, "
        "vakantie=excluded.vakantie, factor=excluded.factor, note=excluded.note, updated_at=excluded.updated_at",
        (date, hours, int(bool(storing)), vakantie or 0, factor or 1, note, updated_at))


def day_out(r) -> dict:
    return dict(date=r["date"], hours=r["hours"], storing=bool(r["storing"]), vakantie=r["vakantie"],
                factor=r["factor"], note=r["note"], updated_at=r["updated_at"])


def week_out(W, settings) -> dict:
    return dict(iso_year=W.iso_year, week=W.week, month=W.month, maand=MAANDEN[W.month - 1],
                dates=[d.isoformat() for d in W.dates], hours=W.hours, storing=W.storing, vakantie=W.vakantie,
                factor=W.factor, total=W.total, gewerkt=W.gewerkt, overuren=W.overuren, storing_dagen=W.storing_days, vakantie_dagen=W.vakantie_days,
                contract=settings["contract_hours"])


@app.get(api + "/ping", dependencies=[Depends(auth.require_api)])
def api_ping():
    return {"ok": True, "server_time": now_iso()}


@app.get(api + "/days", dependencies=[Depends(auth.require_api)])
def api_days(start: str, end: str):
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM days WHERE date BETWEEN ? AND ? ORDER BY date",
                            (dt.date.fromisoformat(start).isoformat(), dt.date.fromisoformat(end).isoformat()))
        return [day_out(r) for r in rows]


@app.put(api + "/days/{date}", dependencies=[Depends(auth.require_api)])
def api_put_day(date: str, body: DayIn):
    d = dt.date.fromisoformat(date).isoformat()
    upd = body.updated_at or now_iso()
    with db.get_conn() as conn:
        cur = conn.execute("SELECT * FROM days WHERE date=?", (d,)).fetchone()
        if cur is not None and cur["updated_at"] > upd:
            # server heeft een nieuwere versie (bv. via web aangepast): die wint
            return JSONResponse(day_out(cur), status_code=409)
        if body.hours is None and not body.storing and not body.vakantie and not body.note and body.factor == 1:
            conn.execute("DELETE FROM days WHERE date=?", (d,))
            return {"date": d, "deleted": True}
        upsert_day(conn, d, body.hours, body.storing, body.vakantie, body.note, upd, body.factor)
        return day_out(conn.execute("SELECT * FROM days WHERE date=?", (d,)).fetchone())


@app.get(api + "/week/{date}", dependencies=[Depends(auth.require_api)])
def api_week(date: str):
    y, w, _ = dt.date.fromisoformat(date).isocalendar()
    with db.get_conn() as conn:
        return week_out(get_week(conn, y, w), get_settings(conn, y))


@app.get(api + "/month/{year}/{month}", dependencies=[Depends(auth.require_api)])
def api_month(year: int, month: int):
    with db.get_conn() as conn:
        Y = build_year(conn, year)
    M = Y["months"][month - 1]
    return dict(year=year, month=month, maand=M.naam, uren=M.uren, overuren=M.overuren,
                gewerkt=M.gewerkt, overuren_euro=M.overuren_euro, storing_dagen=M.storing_days, storing_euro=M.storing_euro,
                netto=M.netto, totaal_netto=M.totaal_netto,
                weeks=[week_out(W, Y["settings"]) for W in M.weeks])


@app.get(api + "/print/{year}/{month}.pdf", dependencies=[Depends(auth.require_api)])
def api_print(year: int, month: int):
    return _pdf(year, [month], f"uren-{year}-{month:02d}.pdf")


@app.get(api + "/app-version", dependencies=[Depends(auth.require_api)])
def api_app_version():
    return app_info() or {}


@app.get(api + "/app.apk", dependencies=[Depends(auth.require_api)])
def api_apk():
    return _apk_response()
