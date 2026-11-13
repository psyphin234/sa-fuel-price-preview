"""
The track record: how close past forecasts were to what happened.

For each of the last MONTHS price changes it gives, per fuel:
- the forecast (Basic Fuel Price part, c/l of price change) with 10 and with 5
  days of the review period still to come, as the site logged it at the time
  (db.prediction_log, which starts on 22 Sep 2026: "logged") or, before then,
  replayed from CEF's history the way the site forecasts (forecast_range.replay:
  "replayed");
- the final Basic Fuel Price part: CEF's average over/(under) recovery for the
  whole period, the figure the forecast aims at;
- the official change, from the prices in CEF's reports either side of it. The
  difference from the final figure is the levy and other government decisions.

A "day still to come" counts days CEF hasn't published, so a logged forecast is
the last one made with CEF's report for that day, its estimates included.
"""
import bfp_model as bm
import forecast_range

STAGES = (10, 5)  # days of the review period still to come
MONTHS = 12


def official_changes(history: list, fuels: list) -> dict:
    """{price change date: {fuel: change in c/l}} from the prices in CEF's reports:
    the last report under each pump price that has every price (CEF sometimes
    corrects one in a later report), against the one before."""
    prices = {}
    for r in sorted(history, key=lambda r: r.report_date):
        if all(r.current_price.get(f) is not None for f in fuels):
            prices[r.pump_price_effective] = r.current_price
    dates = sorted(prices)
    return {new: {f: round(prices[new][f] - prices[old][f], 2) for f in fuels}
            for old, new in zip(dates, dates[1:])}


def build(history: list, logged: list, current_start, fuels: list, follows: dict = None) -> dict:
    """The rows per fuel, newest first. A fuel in `follows` (petrol 93) gets its
    leader's, since its forecast has been the leader's; the frontend says so."""
    follows = follows or {}
    changes = official_changes(history, fuels)
    log = {(l["period_start"], l["period_end"], l["fuel"]): l["predicted_change_c_per_l"] for l in logged}
    periods = forecast_range.finished_periods(history, current_start)
    out = {f: [] for f in fuels if f not in follows}
    for reports in periods:
        closing = reports[-1]
        effective = bm.next_price_change_date(closing.pump_price_effective)
        official = changes.get(effective)
        if official is None:  # not in effect yet, or outside the cache
            continue
        n = len(reports)
        start = reports[0].period_start.isoformat()
        for fuel in out:
            final = closing.avg_over_under.get(fuel)
            if final is None:
                continue
            stages = {}
            for remaining in STAGES:
                if n - remaining < 1:
                    continue
                day = reports[n - remaining - 1].report_date.isoformat()
                value, source = log.get((start, day, fuel)), "logged"
                if value is None:
                    projected = forecast_range.replay(reports, fuel, remaining)
                    if projected is None:
                        continue
                    value, source = -projected, "replayed"
                stages[str(remaining)] = {"value": round(value, 1), "source": source}
            out[fuel].append({
                "effective": effective,
                "period_start": reports[0].period_start,
                "period_end": closing.report_date,
                "stages": stages,
                "final": round(-final, 1),
                "official": official[fuel],
            })
    for fuel in out:
        out[fuel] = out[fuel][::-1][:MONTHS]
    for fuel, leader in follows.items():
        if fuel in fuels and leader in out:
            out[fuel] = out[leader]
    return {"stages": list(STAGES), "logging_since": min((l["recorded_at"][:10] for l in logged), default=None),
            "fuels": out}
