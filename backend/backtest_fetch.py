"""
Downloads CEF's historical daily BFP reports into data/backtest/cef_reports.json
for backtesting the nowcast model. Kept separate from the live database.

Usage:  python backtest_fetch.py 2025-06-01 2026-09-25
"""
import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

import cef_scraper as cef

OUT = Path(__file__).parent.parent / "data" / "backtest" / "cef_reports.json"
URL = "https://cefgroup.co.za/wp-content/uploads/{y}/{m:02d}/Daily-{d:02d}-{mo:02d}-{yr}.pdf"


def candidate_urls(date: dt.date):
    nxt = (date.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    for folder in (date, nxt):
        yield URL.format(y=folder.year, m=folder.month, d=date.day, mo=date.month, yr=date.year)


def fetch(date: dt.date):
    for url in candidate_urls(date):
        try:
            resp = requests.get(url, headers=cef.HEADERS, timeout=30)
        except requests.RequestException as e:
            return date, None, f"error {e}"
        if resp.status_code == 200 and resp.content.startswith(b"%PDF"):
            try:
                rep = cef.parse_pdf(resp.content)
            except Exception as e:
                return date, None, f"parse error {e}"
            if rep is None:
                return date, None, "parse failed"
            return date, rep, url
    return date, None, "not published"


def main(start: dt.date, end: dt.date):
    existing = json.loads(OUT.read_text()) if OUT.exists() else {}
    dates = []
    d = start
    while d <= end:
        if d.isoformat() not in existing:
            dates.append(d)
        d += dt.timedelta(days=1)

    with ThreadPoolExecutor(max_workers=6) as pool:
        for date, rep, info in pool.map(fetch, dates):
            if rep is not None:
                row = {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in rep.__dict__.items()}
                row["url"] = info
                existing[date.isoformat()] = row
            elif info != "not published" or date.weekday() < 5:
                existing[date.isoformat()] = {"missing": info}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(existing, indent=1, sort_keys=True))
    found = sum(1 for v in existing.values() if "missing" not in v)
    print(f"{found} reports, {len(existing) - found} weekdays/errors without a report -> {OUT}")


if __name__ == "__main__":
    main(dt.date.fromisoformat(sys.argv[1]), dt.date.fromisoformat(sys.argv[2]))
