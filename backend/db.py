"""SQLite storage: manual overrides, a cache of parsed CEF daily reports (so we
don't re-fetch/re-parse ~20 PDFs on every page load), and a log of past
predictions so accuracy can be reviewed once a cycle closes."""
import sqlite3
import json
import datetime as dt
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "bfp.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS manual_overrides (
    date TEXT PRIMARY KEY,
    bfp_json TEXT NOT NULL,
    exchange_rate REAL,
    entered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cef_report_cache (
    report_date TEXT PRIMARY KEY,
    report_json TEXT NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prediction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    fuel TEXT NOT NULL,
    blended_avg_over_under REAL NOT NULL,
    predicted_change_c_per_l REAL NOT NULL
);
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def set_manual_override(date: dt.date, bfp: dict, exchange_rate: float = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO manual_overrides (date, bfp_json, exchange_rate, entered_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET bfp_json=excluded.bfp_json, "
            "exchange_rate=excluded.exchange_rate, entered_at=excluded.entered_at",
            (date.isoformat(), json.dumps(bfp), exchange_rate, dt.datetime.now().isoformat()),
        )


def delete_manual_override(date: dt.date):
    with get_conn() as conn:
        conn.execute("DELETE FROM manual_overrides WHERE date = ?", (date.isoformat(),))


def get_manual_overrides(start: dt.date = None, end: dt.date = None) -> dict:
    """Returns {date: {"bfp": {...}, "exchange_rate": ...}}"""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM manual_overrides ORDER BY date").fetchall()
    out = {}
    for r in rows:
        d = dt.date.fromisoformat(r["date"])
        if start and d < start:
            continue
        if end and d > end:
            continue
        out[d] = {"bfp": json.loads(r["bfp_json"]), "exchange_rate": r["exchange_rate"]}
    return out


def cache_report(report_date: dt.date, report_dict: dict):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cef_report_cache (report_date, report_json, cached_at) VALUES (?, ?, ?) "
            "ON CONFLICT(report_date) DO UPDATE SET report_json=excluded.report_json, cached_at=excluded.cached_at",
            (report_date.isoformat(), json.dumps(report_dict, default=str), dt.datetime.now().isoformat()),
        )


def get_cached_report(report_date: dt.date):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT report_json FROM cef_report_cache WHERE report_date = ?", (report_date.isoformat(),)
        ).fetchone()
    return json.loads(row["report_json"]) if row else None


def log_prediction(period_start: dt.date, period_end: dt.date, fuel: str,
                    blended_avg_over_under: float, predicted_change: float):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO prediction_log (recorded_at, period_start, period_end, fuel, "
            "blended_avg_over_under, predicted_change_c_per_l) VALUES (?, ?, ?, ?, ?, ?)",
            (dt.datetime.now().isoformat(), period_start.isoformat(), period_end.isoformat(),
             fuel, blended_avg_over_under, predicted_change),
        )


def get_prediction_history(fuel: str = None, limit: int = 200) -> list:
    with get_conn() as conn:
        if fuel:
            rows = conn.execute(
                "SELECT * FROM prediction_log WHERE fuel = ? ORDER BY recorded_at DESC LIMIT ?",
                (fuel, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM prediction_log ORDER BY recorded_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]
