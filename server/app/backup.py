"""Dagelijkse backup: SQLite-kopie + Excel-export in DATA_DIR/backups, daarna rclone naar OneDrive."""
import datetime as dt
import json
import logging
import os
import sqlite3
import subprocess
from pathlib import Path

from . import db
from .export_xlsx import export_workbook

log = logging.getLogger("backup")

BACKUP_DIR = db.DATA_DIR / "backups"
RCLONE_CONF = Path(os.environ.get("RCLONE_CONFIG", str(db.DATA_DIR / "rclone" / "rclone.conf")))
RCLONE_REMOTE = os.environ.get("RCLONE_REMOTE", "onedrive:UrenBackup")
KEEP_DAYS = int(os.environ.get("BACKUP_KEEP_DAYS", "30"))


def run_backup() -> dict:
    started = dt.datetime.now()
    stamp = started.strftime("%Y-%m-%d")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    result = dict(time=started.isoformat(timespec="seconds"), ok=False, files=[], upload=None, error=None)
    try:
        db_file = BACKUP_DIR / f"uren-{stamp}.db"
        src = db.connect()
        dst = sqlite3.connect(db_file)
        with dst:
            src.backup(dst)
        dst.close()
        xlsx_file = BACKUP_DIR / f"uren-{stamp}.xlsx"
        xlsx_file.write_bytes(export_workbook(src))
        src.close()
        result["files"] = [db_file.name, xlsx_file.name]
        _prune()
        result["upload"] = _upload()
        result["ok"] = result["upload"] in ("ok", "geen rclone-config")
    except Exception as e:  # noqa: BLE001 - status moet altijd opgeslagen worden
        log.exception("backup mislukt")
        result["error"] = str(e)
    with db.get_conn() as conn:
        db.set_meta(conn, "last_backup", json.dumps(result))
    return result


def _prune():
    cutoff = dt.date.today() - dt.timedelta(days=KEEP_DAYS)
    for f in BACKUP_DIR.glob("uren-*.*"):
        try:
            d = dt.date.fromisoformat(f.stem[5:15])
        except ValueError:
            continue
        if d < cutoff:
            f.unlink()


def _upload() -> str:
    if not RCLONE_CONF.exists():
        return "geen rclone-config"
    proc = subprocess.run(
        ["rclone", "copy", str(BACKUP_DIR), RCLONE_REMOTE, "--config", str(RCLONE_CONF)],
        capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError("rclone: " + (proc.stderr.strip().splitlines() or ["onbekende fout"])[-1])
    return "ok"


def last_status() -> dict | None:
    with db.get_conn() as conn:
        v = db.get_meta(conn, "last_backup")
    return json.loads(v) if v else None
