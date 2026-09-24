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

CREATE TABLE IF NOT EXISTS estimate_log (
    date TEXT NOT NULL,
    fuel TEXT NOT NULL,
    estimated_bfp REAL NOT NULL,
    logged_at TEXT NOT NULL,
    PRIMARY KEY (date, fuel)
);

CREATE TABLE IF NOT EXISTS benchmark_daily (
    trade_date TEXT NOT NULL,
    name TEXT NOT NULL,
    pct_change REAL NOT NULL,
    price REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, name)
);

CREATE TABLE IF NOT EXISTS cef_release_log (
    report_date TEXT PRIMARY KEY,
    last_missing_at TEXT,
    first_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS accuracy_log (
    date TEXT NOT NULL,
    fuel TEXT NOT NULL,
    estimated_bfp REAL NOT NULL,
    official_bfp REAL NOT NULL,
    error_c_per_l REAL NOT NULL,
    pct_error REAL,
    reconciled_at TEXT NOT NULL,
    PRIMARY KEY (date, fuel)
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


def upsert_estimate(date: dt.date, fuel: str, estimated_bfp: float):
    """Remembers today's estimated BFP for (date, fuel) so its accuracy can be
    checked once CEF publishes the real figure for that date."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO estimate_log (date, fuel, estimated_bfp, logged_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(date, fuel) DO UPDATE SET estimated_bfp=excluded.estimated_bfp, logged_at=excluded.logged_at",
            (date.isoformat(), fuel, estimated_bfp, dt.datetime.now().isoformat()),
        )


def pop_estimate(date: dt.date, fuel: str):
    """Returns and removes the logged estimate for (date, fuel), or None if none was logged."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT estimated_bfp FROM estimate_log WHERE date = ? AND fuel = ?", (date.isoformat(), fuel)
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM estimate_log WHERE date = ? AND fuel = ?", (date.isoformat(), fuel))
        return row["estimated_bfp"]


def log_accuracy(date: dt.date, fuel: str, estimated_bfp: float, official_bfp: float):
    error = official_bfp - estimated_bfp
    pct_error = (error / official_bfp) if official_bfp else None
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO accuracy_log (date, fuel, estimated_bfp, official_bfp, error_c_per_l, pct_error, reconciled_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(date, fuel) DO NOTHING",
            (date.isoformat(), fuel, estimated_bfp, official_bfp, error, pct_error, dt.datetime.now().isoformat()),
        )


def get_accuracy_by_date(start: dt.date, end: dt.date) -> dict:
    """Returns {(date_iso, fuel): row} for reconciled estimates within [start, end]."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM accuracy_log WHERE date BETWEEN ? AND ?", (start.isoformat(), end.isoformat())
        ).fetchall()
    return {(r["date"], r["fuel"]): dict(r) for r in rows}


def get_accuracy_records(limit: int = 90) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM accuracy_log ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_benchmark_day(trade_date: dt.date, name: str, pct_change: float, price: float):
    """Stores a benchmark's roll-safe day-over-day move for its trading date. Later
    runs on the same trading date overwrite it, so once the day is over the stored
    value is that day's final move."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO benchmark_daily (trade_date, name, pct_change, price, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(trade_date, name) DO UPDATE SET pct_change=excluded.pct_change, "
            "price=excluded.price, updated_at=excluded.updated_at",
            (trade_date.isoformat(), name, pct_change, price, dt.datetime.now().isoformat()),
        )


def get_benchmark_days(since: dt.date) -> dict:
    """Returns {name: {date: pct_change}} for trading dates on or after `since`."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT trade_date, name, pct_change FROM benchmark_daily WHERE trade_date >= ?", (since.isoformat(),)
        ).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["name"], {})[dt.date.fromisoformat(r["trade_date"])] = r["pct_change"]
    return out


def note_report_missing(report_date: dt.date):
    """Records a check that found no CEF report yet for `report_date`."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cef_release_log (report_date, last_missing_at) VALUES (?, ?) "
            "ON CONFLICT(report_date) DO UPDATE SET last_missing_at=excluded.last_missing_at "
            "WHERE cef_release_log.first_seen_at IS NULL",
            (report_date.isoformat(), dt.datetime.now().isoformat(timespec="seconds")),
        )


def note_report_found(report_date: dt.date):
    """Records the first time a CEF report for `report_date` was found."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cef_release_log (report_date, first_seen_at) VALUES (?, ?) "
            "ON CONFLICT(report_date) DO UPDATE SET first_seen_at=excluded.first_seen_at "
            "WHERE cef_release_log.first_seen_at IS NULL",
            (report_date.isoformat(), dt.datetime.now().isoformat(timespec="seconds")),
        )


def get_release_log() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM cef_release_log WHERE first_seen_at IS NOT NULL ORDER BY report_date"
        ).fetchall()
    return [dict(r) for r in rows]
