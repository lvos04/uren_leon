"""Dagelijkse backup: SQLite-kopie + Excel-export in DATA_DIR/backups, daarna rclone naar OneDrive.

Alle instellingen staan in de database en zijn te wijzigen in de web-app (Instellingen -> Backup).
"""
import datetime as dt
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

from . import db
from .export_xlsx import export_workbook

log = logging.getLogger("backup")

BACKUP_DIR = db.DATA_DIR / "backups"
RCLONE_CONF = Path(os.environ.get("RCLONE_CONFIG", str(db.DATA_DIR / "rclone" / "rclone.conf")))
REMOTE_NAME = "onedrive"
NAME_RE = re.compile(r"^uren-\d{4}-\d{2}-\d{2}(-\d{6})?\.(db|xlsx)$")

DEFAULTS = {"backup_time": "03:00", "backup_folder": "UrenBackup", "backup_keep_days": "30", "month_pdf": "1"}
MONTH_DIR = db.DATA_DIR / "maandoverzichten"
MONTH_RE = re.compile(r"^uren-\d{4}-\d{2}\.pdf$")


def get_settings() -> dict:
    with db.get_conn() as conn:
        return {k: db.get_meta(conn, k, v) for k, v in DEFAULTS.items()}


def save_settings(time: str, folder: str, keep_days: int, month_pdf: bool = True) -> None:
    hh, mm = time.split(":")
    t = f"{int(hh):02d}:{int(mm):02d}"
    folder = folder.strip().strip("/") or "UrenBackup"
    if not re.fullmatch(r"[\w\- /]+", folder):
        raise ValueError("Mapnaam mag alleen letters, cijfers, spaties, - en _ bevatten")
    with db.get_conn() as conn:
        db.set_meta(conn, "backup_time", t)
        db.set_meta(conn, "backup_folder", folder)
        db.set_meta(conn, "backup_keep_days", str(max(1, int(keep_days))))
        db.set_meta(conn, "month_pdf", "1" if month_pdf else "0")


def onedrive_linked() -> bool:
    return RCLONE_CONF.exists() and f"[{REMOTE_NAME}]" in RCLONE_CONF.read_text()


def remote_path() -> str:
    return f"{REMOTE_NAME}:{get_settings()['backup_folder']}"


def run_backup() -> dict:
    started = dt.datetime.now()
    stamp = started.strftime("%Y-%m-%d")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    result = dict(time=started.isoformat(timespec="seconds"), ok=False, files=[], upload=None, error=None)
    try:
        db_file = BACKUP_DIR / f"uren-{stamp}.db"
        _copy_db(db_file)
        src = db.connect()
        xlsx_file = BACKUP_DIR / f"uren-{stamp}.xlsx"
        xlsx_file.write_bytes(export_workbook(src))
        src.close()
        result["files"] = [db_file.name, xlsx_file.name]
        _prune()
        result["upload"] = _upload()
        result["ok"] = result["upload"] in ("ok", "OneDrive niet gekoppeld")
    except Exception as e:  # noqa: BLE001 - status moet altijd opgeslagen worden
        log.exception("backup mislukt")
        result["error"] = str(e)
    with db.get_conn() as conn:
        db.set_meta(conn, "last_backup", json.dumps(result))
    return result


def _copy_db(target: Path) -> None:
    src = db.connect()
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()


def _prune():
    keep = int(get_settings()["backup_keep_days"])
    cutoff = dt.date.today() - dt.timedelta(days=keep)
    for f in BACKUP_DIR.glob("uren-*.*"):
        try:
            d = dt.date.fromisoformat(f.name[5:15])
        except ValueError:
            continue
        if d < cutoff:
            f.unlink()


def rclone(*args, timeout=600) -> subprocess.CompletedProcess:
    return subprocess.run(["rclone", *args, "--config", str(RCLONE_CONF)],
                          capture_output=True, text=True, timeout=timeout)


def _upload() -> str:
    if not onedrive_linked():
        return "OneDrive niet gekoppeld"
    proc = rclone("copy", str(BACKUP_DIR), remote_path(), "--include", "uren-*")
    if proc.returncode != 0:
        raise RuntimeError("OneDrive: " + (proc.stderr.strip().splitlines() or ["onbekende fout"])[-1])
    return "ok"


def last_status() -> dict | None:
    with db.get_conn() as conn:
        v = db.get_meta(conn, "last_backup")
    return json.loads(v) if v else None


def list_backups() -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    out = []
    for f in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if NAME_RE.match(f.name):
            out.append(dict(name=f.name, size=f.stat().st_size, kind=f.suffix[1:]))
    return out


def backup_file(name: str) -> Path:
    if not NAME_RE.match(name):
        raise FileNotFoundError(name)
    p = BACKUP_DIR / name
    if not p.exists():
        raise FileNotFoundError(name)
    return p


def restore(name: str) -> str:
    """Zet een .db-backup terug. Maakt eerst een veiligheidskopie van de huidige gegevens."""
    src = backup_file(name)
    if src.suffix != ".db":
        raise ValueError("Alleen .db-bestanden kunnen worden teruggezet")
    check = sqlite3.connect(src)
    try:
        check.execute("SELECT count(*) FROM days").fetchone()
    finally:
        check.close()
    safety = BACKUP_DIR / f"uren-{dt.datetime.now():%Y-%m-%d-%H%M%S}.db"
    _copy_db(safety)
    # wachtwoord, tokens en instellingen van nu bewaren (niet terugdraaien naar die van de backup)
    live = db.connect()
    meta = live.execute("SELECT key, value FROM meta").fetchall()
    tokens = live.execute("SELECT name, token_hash, created_at FROM tokens").fetchall()
    live.close()
    tmp = db.DB_PATH.with_suffix(".restore")
    shutil.copyfile(src, tmp)
    restored = sqlite3.connect(tmp)
    live = db.connect()
    with live:
        restored.backup(live)
    restored.close()
    live.close()
    tmp.unlink()
    db.init_db()
    with db.get_conn() as conn:
        for k, v in meta:
            if k != "last_backup":
                db.set_meta(conn, k, v)
        conn.execute("DELETE FROM tokens")
        conn.executemany("INSERT INTO tokens(name, token_hash, created_at) VALUES(?,?,?)",
                         [tuple(t) for t in tokens])
    return safety.name


# ---------------------------------------------------------------- maandoverzicht als PDF
def send_month_pdf(year: int, month: int) -> dict:
    """Maak de maand-PDF en zet hem (als OneDrive gekoppeld is) in <backup-map>/Maandoverzichten."""
    from .printing import render_pdf
    MONTH_DIR.mkdir(parents=True, exist_ok=True)
    f = MONTH_DIR / f"uren-{year}-{month:02d}.pdf"
    result = dict(time=dt.datetime.now().isoformat(timespec="seconds"), file=f.name, upload=None, error=None)
    try:
        conn = db.connect()
        try:
            f.write_bytes(render_pdf(conn, year, [month]))
        finally:
            conn.close()
        if onedrive_linked():
            p = rclone("copy", str(f), remote_path() + "/Maandoverzichten")
            if p.returncode != 0:
                raise RuntimeError("OneDrive: " + (p.stderr.strip().splitlines() or ["onbekende fout"])[-1])
            result["upload"] = "ok"
        else:
            result["upload"] = "OneDrive niet gekoppeld"
    except Exception as e:  # noqa: BLE001
        log.exception("maandoverzicht mislukt")
        result["error"] = str(e)
    with db.get_conn() as conn:
        db.set_meta(conn, "last_month_pdf", json.dumps(result))
    return result


def send_previous_month() -> dict | None:
    if get_settings()["month_pdf"] != "1":
        return None
    first = dt.date.today().replace(day=1)
    prev = first - dt.timedelta(days=1)
    return send_month_pdf(prev.year, prev.month)


def last_month_pdf() -> dict | None:
    with db.get_conn() as conn:
        v = db.get_meta(conn, "last_month_pdf")
    return json.loads(v) if v else None


def list_month_pdfs() -> list[str]:
    if not MONTH_DIR.exists():
        return []
    return sorted((f.name for f in MONTH_DIR.iterdir() if MONTH_RE.match(f.name)), reverse=True)


def month_pdf_file(name: str) -> Path:
    if not MONTH_RE.match(name) or not (MONTH_DIR / name).exists():
        raise FileNotFoundError(name)
    return MONTH_DIR / name
