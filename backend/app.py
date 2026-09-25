import datetime as dt
import json
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import cef_scraper as cef
import market_data as md
import bfp_model as bm
import db
import accuracy
import nowcast

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = Flask(__name__, static_folder=None)
db.init_db()

_benchmark_cache = {"data": None, "fetched_at": None}
BENCHMARK_TTL_SECONDS = 120
_market_cache = {"data": None, "fetched_at": None}
MARKET_TTL_SECONDS = 600
HISTORY_DAYS = 380            # enough weekdays for nowcast.TRAIN_WINDOW
HISTORY_BACKFILL_PER_RUN = 30  # keeps a cold start from making one run very slow


def json_default(o):
    if isinstance(o, dt.date):
        return o.isoformat()
    if hasattr(o, "__dict__"):
        return o.__dict__
    raise TypeError(f"Not serializable: {o!r}")


def dumps(obj, **kw):
    return json.dumps(obj, default=json_default, **kw)


class JSONResponse:
    """Small helper so we can return dataclasses / date-containing dicts straight from Flask."""
    @staticmethod
    def make(obj, status=200):
        return app.response_class(dumps(obj), status=status, mimetype="application/json")


def _report_from_cache(cached: dict) -> cef.DailyReport:
    for key in ("report_date", "period_start", "period_end", "reference_valid_from", "pump_price_effective"):
        cached[key] = dt.date.fromisoformat(cached[key])
    return cef.DailyReport(**cached)


def get_report_cached(date: dt.date):
    cached = db.get_cached_report(date)
    if cached:
        return _report_from_cache(cached)
    rep = cef.fetch_and_parse(date)
    if rep:
        db.cache_report(date, rep.__dict__)
        db.note_report_found(date)
    else:
        db.note_report_missing(date)
    return rep


def get_latest_report():
    d = dt.date.today()
    for _ in range(10):
        rep = get_report_cached(d)
        if rep is not None:
            return rep
        d -= dt.timedelta(days=1)
    return None


def get_period_reports(period_start: dt.date, period_end: dt.date):
    reports = []
    d = period_start
    while d <= period_end:
        rep = get_report_cached(d) if bm.is_business_day(d) else None
        if rep is not None:
            reports.append(rep)
        d += dt.timedelta(days=1)
    return reports


def get_benchmarks(force=False):
    now = dt.datetime.now()
    if (not force and _benchmark_cache["data"] and _benchmark_cache["fetched_at"]
            and (now - _benchmark_cache["fetched_at"]).total_seconds() < BENCHMARK_TTL_SECONDS):
        return _benchmark_cache["data"]
    data = md.fetch_all_benchmarks()
    _benchmark_cache["data"] = data
    _benchmark_cache["fetched_at"] = now
    return data


def get_market():
    now = dt.datetime.now()
    if (_market_cache["data"] and _market_cache["fetched_at"]
            and (now - _market_cache["fetched_at"]).total_seconds() < MARKET_TTL_SECONDS):
        return _market_cache["data"]
    data = nowcast.fetch_market()
    _market_cache["data"] = data
    _market_cache["fetched_at"] = now
    return data


def get_history_reports(end: dt.date) -> list:
    """Official reports for the last HISTORY_DAYS, used to fit the nowcast. Fills
    gaps in the local cache a few days per run; days CEF never published are
    simply retried later (there are almost none)."""
    start = end - dt.timedelta(days=HISTORY_DAYS)
    cached = {r["report_date"]: r for r in db.get_cached_reports(start, end)}
    fetched = 0
    d = end
    while d >= start and fetched < HISTORY_BACKFILL_PER_RUN:
        if bm.is_business_day(d) and d.isoformat() not in cached:
            rep = cef.fetch_and_parse(d)
            fetched += 1
            if rep:
                db.cache_report(d, rep.__dict__)
                cached[d.isoformat()] = db.get_cached_report(d)
        d -= dt.timedelta(days=1)
    return [_report_from_cache(dict(cached[k])) for k in sorted(cached)]


def manual_overrides_dict():
    raw = db.get_manual_overrides()
    return raw  # already {date: {"bfp": {...}, "exchange_rate": ...}}


def build_status_data():
    """Builds the full payload the dashboard needs. Shared by the local Flask
    API and publish.py (the static-site publisher) so both stay identical."""
    latest = get_latest_report()
    if latest is None:
        return None

    benchmarks = get_benchmarks()
    overrides = manual_overrides_dict()
    today = dt.date.today()

    market = get_market()
    weights = nowcast.fit_weights(get_history_reports(latest.report_date), market, cef.FUELS)

    predictions = {}
    for fuel in cef.FUELS:
        pred = bm.build_prediction(fuel, latest, market, weights, manual_overrides=overrides, today=today)
        predictions[fuel] = pred
        db.log_prediction(latest.period_start, latest.period_end, fuel,
                           pred.blended_avg_over_under, pred.predicted_pump_price_change_c_per_l)

    period_reports = get_period_reports(latest.period_start, latest.period_end)
    daily_series = {
        fuel: [
            {
                "date": r.report_date,
                "bfp": r.bfp.get(fuel),
                "unit_over_under": r.unit_over_under.get(fuel),
                "source": "cef_official",
            }
            for r in period_reports
        ]
        for fuel in cef.FUELS
    }
    # append estimated/manual gap days from each fuel's prediction onto the series
    for fuel in cef.FUELS:
        for day in predictions[fuel].estimated_days + predictions[fuel].manual_days:
            daily_series[fuel].append({
                "date": day["date"],
                "bfp": day["bfp"].get(fuel),
                "unit_over_under": day["unit_over_under"].get(fuel),
                "source": day["source"],
            })

    # USD/ZAR is the same across fuels, so build its own series once rather
    # than repeating it inside each fuel's daily_series.
    exchange_rate_series = [
        {"date": r.report_date, "rate": r.exchange_rate, "source": "cef_official"}
        for r in period_reports
    ]
    first_fuel = cef.FUELS[0]
    for day in predictions[first_fuel].estimated_days + predictions[first_fuel].manual_days:
        exchange_rate_series.append({
            "date": day["date"],
            "rate": day.get("exchange_rate"),
            "source": day["source"],
        })
    exchange_rate_series.sort(key=lambda d: d["date"])

    # Accuracy tracking: remember today's guesses, check yesterday's guesses
    # against whatever CEF has now officially published, summarize the track record.
    accuracy.log_estimates(predictions)
    accuracy.reconcile(period_reports)
    accuracy_summary = accuracy.get_accuracy_summary()

    # Official days that were estimated first carry that earlier estimate, so the
    # UI can show how close it was.
    checked = db.get_accuracy_by_date(latest.period_start, latest.period_end)
    for fuel in cef.FUELS:
        for entry in daily_series[fuel]:
            if entry["source"] != "cef_official":
                continue
            rec = checked.get((entry["date"].isoformat(), fuel))
            if rec:
                entry["estimate"] = {
                    "bfp": rec["estimated_bfp"],
                    "error_c_per_l": round(rec["error_c_per_l"], 3),
                    "pct_error": round(rec["pct_error"] * 100, 2) if rec["pct_error"] is not None else None,
                }

    # A weekday CEF skipped (very rare) gets an indicative estimate for the table
    # only: kept out of the prediction average, the charts and accuracy tracking,
    # since no official figure will ever exist for it.
    indicative_days = {fuel: [] for fuel in cef.FUELS}
    d = latest.period_start
    while d <= today:
        base = next((r for r in reversed(period_reports) if r.report_date < d), None)
        if base is not None and bm.is_business_day(d):
            est = bm.nowcast_single_day(base, d, market, weights)
            for fuel in cef.FUELS:
                if d not in {e["date"] for e in daily_series[fuel]} and fuel in est.bfp:
                    indicative_days[fuel].append({
                        "date": d,
                        "bfp": est.bfp[fuel],
                        "unit_over_under": est.unit_over_under.get(fuel),
                    })
        d += dt.timedelta(days=1)

    next_change = bm.next_price_change_date(latest.pump_price_effective)

    return {
        "latest_official_report": latest,
        "benchmarks": benchmarks,
        "fuels": cef.FUEL_LABELS,
        "predictions": predictions,
        "daily_series": daily_series,
        "indicative_days": indicative_days,
        "exchange_rate_series": exchange_rate_series,
        "current_exchange_rate": benchmarks.get("usdzar", {}).get("price"),
        "accuracy": accuracy_summary,
        "next_price_change_date": next_change,
        "days_until_next_price_change": (next_change - today).days,
        "generated_at": dt.datetime.now(),
    }


@app.route("/api/status")
def api_status():
    data = build_status_data()
    if data is None:
        return JSONResponse.make({"error": "Could not reach CEF's site or parse any recent report."}, 502)
    return JSONResponse.make(data)


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    get_benchmarks(force=True)
    latest = None
    d = dt.date.today()
    for _ in range(10):
        rep = cef.fetch_and_parse(d)
        if rep is not None:
            db.cache_report(d, rep.__dict__)
            db.note_report_found(d)
            latest = rep
            break
        db.note_report_missing(d)
        d -= dt.timedelta(days=1)
    if latest is None:
        return JSONResponse.make({"error": "No new report found"}, 502)
    dd = latest.period_start
    while dd <= latest.period_end:
        if db.get_cached_report(dd) is None:
            rep = cef.fetch_and_parse(dd)
            if rep is not None:
                db.cache_report(dd, rep.__dict__)
        dd += dt.timedelta(days=1)
    return JSONResponse.make({"ok": True, "latest_report_date": latest.report_date})


@app.route("/api/manual-override", methods=["POST"])
def api_manual_override():
    body = request.get_json(force=True)
    try:
        date = dt.date.fromisoformat(body["date"])
        bfp = {k: float(v) for k, v in body.get("bfp", {}).items() if v not in (None, "")}
        exchange_rate = body.get("exchange_rate")
        exchange_rate = float(exchange_rate) if exchange_rate not in (None, "") else None
    except (KeyError, ValueError, TypeError) as e:
        return JSONResponse.make({"error": f"Invalid payload: {e}"}, 400)
    if not bfp:
        return JSONResponse.make({"error": "Provide at least one fuel BFP value"}, 400)
    db.set_manual_override(date, bfp, exchange_rate)
    return JSONResponse.make({"ok": True})


@app.route("/api/manual-override/<date_str>", methods=["DELETE"])
def api_delete_manual_override(date_str):
    try:
        date = dt.date.fromisoformat(date_str)
    except ValueError:
        return JSONResponse.make({"error": "Invalid date"}, 400)
    db.delete_manual_override(date)
    return JSONResponse.make({"ok": True})


@app.route("/api/manual-overrides")
def api_get_manual_overrides():
    overrides = manual_overrides_dict()
    return JSONResponse.make({d.isoformat(): v for d, v in overrides.items()})


@app.route("/api/history")
def api_history():
    fuel = request.args.get("fuel")
    return JSONResponse.make(db.get_prediction_history(fuel=fuel))


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    # debug=True gives auto-reload + tracebacks while you're editing; set False for
    # quieter day-to-day use. Bound to localhost only either way.
    app.run(debug=True, port=5057)
