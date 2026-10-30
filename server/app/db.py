"""SQLite opslag. Eén bestand in DATA_DIR (standaard /data)."""
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "uren.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS days (
    date TEXT PRIMARY KEY,              -- YYYY-MM-DD
    hours REAL,                         -- gewerkte uren (NULL = niet ingevuld)
    storing INTEGER NOT NULL DEFAULT 0, -- storingsdienst die dag
    vakantie REAL NOT NULL DEFAULT 0,   -- vakantiedag (1 = hele dag, 0.5 = halve)
    factor REAL NOT NULL DEFAULT 1,     -- uitbetaling overuren van deze dag: 1, 1.5 of 2 (zon-/feestdag)
    note TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS weeks (
    iso_year INTEGER NOT NULL,
    week INTEGER NOT NULL,
    month INTEGER,                      -- handmatige maand-toewijzing (NULL = automatisch)
    storing_extra INTEGER NOT NULL DEFAULT 0,  -- storingsdagen zonder dag (uit Excel-import)
    vakantie_extra REAL NOT NULL DEFAULT 0,    -- vakantiedagen zonder dag (uit Excel-import)
    PRIMARY KEY (iso_year, week)
);
CREATE TABLE IF NOT EXISTS months (
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    bruto REAL,
    netto REAL,
    schaal INTEGER NOT NULL DEFAULT 1,  -- overuurschaal 1 of 2
    PRIMARY KEY (year, month)
);
CREATE TABLE IF NOT EXISTS years (
    year INTEGER PRIMARY KEY,
    contract_hours REAL NOT NULL DEFAULT 40,
    rate1 REAL NOT NULL DEFAULT 15,
    rate2 REAL NOT NULL DEFAULT 17,
    storing_rate REAL NOT NULL DEFAULT 10,
    vakantie_totaal REAL NOT NULL DEFAULT 21,
    loonheffingskorting INTEGER NOT NULL DEFAULT 1,
    situatie TEXT NOT NULL DEFAULT 'standard'
);
CREATE TABLE IF NOT EXISTS payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(days)")}
        if "factor" not in cols:
            conn.execute("ALTER TABLE days ADD COLUMN factor REAL NOT NULL DEFAULT 1")


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def session_secret() -> str:
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    with get_conn() as conn:
        s = get_meta(conn, "secret_key")
        if not s:
            s = secrets.token_hex(32)
            set_meta(conn, "secret_key", s)
        return s
