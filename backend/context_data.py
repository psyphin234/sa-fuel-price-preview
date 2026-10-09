"""
Background context for the "Oil and the Strait of Hormuz" section, shown below
everything else on the site. None of this feeds the prediction model.

- Brent futures: Yahoo Finance BZ=F daily closes (the same symbol as
  market_data.py), the price for oil delivered in about two months.
- Brent physical spot: the EIA's daily "Europe Brent Spot Price FOB" (Dated
  Brent, series RBRTE), scraped from its history page. No key needed. The EIA
  publishes it weekly (usually Wednesdays), so it runs a few days behind.
- Strait of Hormuz traffic: IMF PortWatch's daily ship transits (chokepoint6),
  from its public ArcGIS feed. No key needed. It runs about 5 days behind, is
  revised afterwards, and only counts ships broadcasting on AIS, so during the
  2026 conflict it undercounts: Lloyd's List, Kpler and Windward, which add back
  "dark" crossings, counted several times more in September 2026.

Each part is cached in data/context_cache.json for CACHE_TTL_HOURS, because
publish.py runs in a fresh process up to five times an hour. If a fetch fails,
the last good copy is kept (it carries its own "data to" date, which the site
shows); with no copy at all, that part is None and the site hides it.
"""
import datetime as dt
import html
import json
import re
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BFP-preview-tool/1.0"}
CACHE_PATH = Path(__file__).parent.parent / "data" / "context_cache.json"
CACHE_TTL_HOURS = 3

BRENT_DAYS = 120
YF_BRENT_URL = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F"
EIA_BRENT_URL = "https://www.eia.gov/dnav/pet/hist/RBRTED.htm"

PORTWATCH_URL = ("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
                 "Daily_Chokepoints_Data/FeatureServer/0/query")
HORMUZ_PORTID = "chokepoint6"
HORMUZ_FROM = dt.date(2025, 10, 1)
# The Iran war began on 28 February 2026 (Baird Maritime / Kpler; the IRGC
# declared the strait closed on 2 March). "Normal" is the year before that.
CONFLICT_START = dt.date(2026, 2, 28)


def _brent_futures() -> dict:
    resp = requests.get(YF_BRENT_URL, headers=HEADERS, params={"range": "6mo", "interval": "1d"}, timeout=30)
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    offset = result["meta"].get("gmtoffset", 0)
    points = {}
    for ts, close in zip(result["timestamp"], result["indicators"]["quote"][0]["close"]):
        if close is not None:
            day = dt.datetime.fromtimestamp(ts + offset, dt.timezone.utc).date()
            points[day.isoformat()] = round(close, 2)
    series = sorted(points.items())[-BRENT_DAYS:]
    if len(series) < 10:
        raise ValueError("too few Brent futures points")
    return {"series": [list(p) for p in series], "data_to": series[-1][0]}


_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _brent_spot() -> dict:
    """Parses the EIA history table: one row per week, "2026 Sep-28 to Oct- 2",
    then five cells for Monday to Friday (empty on holidays)."""
    resp = requests.get(EIA_BRENT_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    text = resp.text
    points = []
    for m in re.finditer(r"<td class='B6'>(.*?)</td>((?:\s*<td class='B3'>[^<]*</td>){5})", text):
        label = html.unescape(m.group(1)).replace("\xa0", " ").strip()
        wk = re.match(r"(\d{4}) ([A-Z][a-z]{2})-\s*(\d+) to", label)
        if not wk:
            continue
        monday = dt.date(int(wk.group(1)), _MONTHS[wk.group(2)], int(wk.group(3)))
        cells = re.findall(r"<td class='B3'>([^<]*)</td>", m.group(2))
        for i, cell in enumerate(cells):
            try:
                points.append([(monday + dt.timedelta(days=i)).isoformat(), round(float(cell), 2)])
            except ValueError:
                pass
    points = points[-BRENT_DAYS:]
    if len(points) < 10:
        raise ValueError("too few EIA Brent spot points")
    release = re.search(r"Release Date:\s*([\d/]+)", text)
    return {"series": points, "data_to": points[-1][0],
            "released": release.group(1) if release else None}


def _hormuz() -> dict:
    rows, offset = [], 0
    while True:
        resp = requests.get(PORTWATCH_URL, headers=HEADERS, timeout=60, params={
            "where": f"portid='{HORMUZ_PORTID}' AND date >= DATE '{CONFLICT_START - dt.timedelta(days=365)}'",
            "outFields": "date,n_total,n_tanker",
            "orderByFields": "date ASC",
            "resultOffset": offset,
            "resultRecordCount": 2000,
            "f": "json",
        })
        resp.raise_for_status()
        page = resp.json()
        if "error" in page:
            raise ValueError(f"PortWatch: {page['error']}")
        feats = [f["attributes"] for f in page.get("features", [])]
        rows += feats
        if not page.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)

    days = []
    for r in rows:
        d = r["date"]
        day = (dt.datetime.fromtimestamp(d / 1000, dt.timezone.utc).date() if isinstance(d, (int, float))
               else dt.date.fromisoformat(str(d)[:10]))
        days.append((day, r["n_total"] or 0, r["n_tanker"] or 0))
    days.sort()
    before = [n for day, n, _ in days if CONFLICT_START - dt.timedelta(days=365) <= day < CONFLICT_START]
    if len(days) < 30 or len(before) < 300:
        raise ValueError("too few PortWatch Hormuz days")

    shown = [d for d in days if d[0] >= HORMUZ_FROM]
    last7 = shown[-7:]
    return {
        "series": [[day.isoformat(), n, t] for day, n, t in shown],
        "data_to": shown[-1][0].isoformat(),
        "avg_7d": round(sum(n for _, n, _ in last7) / len(last7), 1),
        "tanker_avg_7d": round(sum(t for _, _, t in last7) / len(last7), 1),
        "normal_per_day": round(sum(before) / len(before), 1),
        "normal_from": (CONFLICT_START - dt.timedelta(days=365)).isoformat(),
        "conflict_start": CONFLICT_START.isoformat(),
    }


PARTS = {"brent_futures": _brent_futures, "brent_spot": _brent_spot, "hormuz": _hormuz}


def get_context() -> dict:
    try:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    now = dt.datetime.now()
    changed = False
    for name, fetch in PARTS.items():
        entry = cache.get(name) or {}
        fetched = entry.get("fetched_at")
        fresh = fetched and (now - dt.datetime.fromisoformat(fetched)).total_seconds() < CACHE_TTL_HOURS * 3600
        if fresh:
            continue
        try:
            cache[name] = {"data": fetch(), "fetched_at": now.isoformat(timespec="seconds")}
        except Exception as e:  # keep the last good copy
            entry["error"] = str(e)[:200]
            entry["fetched_at"] = now.isoformat(timespec="seconds")  # don't retry every run
            if "data" not in entry:
                entry["data"] = None
            cache[name] = entry
        changed = True
    if changed:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    return {name: (cache.get(name) or {}).get("data") for name in PARTS}


if __name__ == "__main__":
    ctx = get_context()
    for name, part in ctx.items():
        if part is None:
            print(name, "NONE")
            continue
        s = part["series"]
        print(name, len(s), "points, data to", part["data_to"], "| last 3:", s[-3:],
              {k: v for k, v in part.items() if k not in ("series",)})
