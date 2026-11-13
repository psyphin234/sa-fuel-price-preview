"""
What's moving the Basic Fuel Price part of a price change: fuel prices abroad (in
dollars) or the rand. Split the way the DMPR splits it in its monthly
announcement:

    rand part    = the period's average BFP x (1 - last period's average R/$ / this period's)
    product part = the rest of the period's average over/(under) recovery

That reproduces every figure in the DMPR's November 2026 statement to the cent,
for the grade each was quoted for: petrol 80.41 c/l (product, from petrol 93) and
36.93 c/l (rand, from petrol 95), diesel 94.22 (0.05%) and 49.00 (0.005%),
paraffin 225.23 and 49.26. The rand averages are each review period's mean of
CEF's daily exchange rate.

Used by app.py for the live forecast (with this tool's estimates for unpublished
days and the rest of the period held at the latest figures) and by month_pages.py
for past months (CEF's own figures).
"""
import datetime as dt


def _get(report, key):
    """A field of a report, whether it's a DailyReport (app.py) or a cached dict
    (month_pages.py)."""
    return report[key] if isinstance(report, dict) else getattr(report, key)


def _date(value) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(value)


def split(total: float, avg_bfp: float, fx_prev: float, fx_cur: float):
    """{"product", "rand"} in c/l of price change (positive = up), adding up to
    `total`; None if a figure is missing."""
    if None in (total, avg_bfp, fx_prev, fx_cur) or not fx_cur:
        return None
    rand = avg_bfp * (1 - fx_prev / fx_cur)
    return {"product": round(total - rand, 2), "rand": round(rand, 2)}


def period_rates(reports: list) -> dict:
    """{review period start: average R/$ over its days}, for periods whose first
    day is in `reports` (so the average covers the whole period so far)."""
    by_start = {}
    for r in reports:
        by_start.setdefault(_date(_get(r, "period_start")), []).append(r)
    rates = {}
    for start, rs in by_start.items():
        rs = sorted(rs, key=lambda r: _date(_get(r, "report_date")))
        fx = [_get(r, "exchange_rate") for r in rs if _get(r, "exchange_rate")]
        if _date(_get(rs[0], "report_date")) == start and fx:
            rates[start] = sum(fx) / len(fx)
    return rates


def live(period_reports: list, predictions: dict, history: list, period_start: dt.date,
         fuels: list, follows: dict = None):
    """The split of each fuel's forecast (Basic Fuel Price part only), over the
    whole review period as the forecast sees it: CEF's days, this tool's estimates,
    and the rest of the period at the latest BFP and exchange rate. A fuel in
    `follows` gets its leader's, since its forecast is the leader's. None if the
    last period's exchange rate isn't known."""
    follows = follows or {}
    earlier = [r for r in history if r.period_start < period_start]
    rates = period_rates(earlier)
    if not rates:
        return None
    prev_start = max(rates)
    fx_prev = rates[prev_start]
    prev_close = max((r for r in earlier if r.period_start == prev_start), key=lambda r: r.report_date)

    lead = predictions[fuels[0]]
    extra = lead.estimated_days + lead.manual_days
    fx_days = [r.exchange_rate for r in period_reports if r.exchange_rate]
    fx_days += [d.get("exchange_rate") or (fx_days[-1] if fx_days else None) for d in extra]
    fx_days = [x for x in fx_days if x]
    if not fx_days:
        return None
    fx_days += [fx_days[-1]] * lead.projected_days_count
    fx_cur = sum(fx_days) / len(fx_days)

    out = {}
    for fuel in fuels:
        if fuel in follows:
            continue
        pred = predictions[fuel]
        bfp = [r.bfp.get(fuel) for r in period_reports]
        bfp += [d["bfp"].get(fuel) for d in pred.estimated_days + pred.manual_days]
        bfp = [b for b in bfp if b is not None]
        if not bfp:
            continue
        bfp += [bfp[-1]] * pred.projected_days_count
        avg_bfp = sum(bfp) / len(bfp)
        total = -pred.projected_avg_over_under
        parts = split(total, avg_bfp, fx_prev, fx_cur)
        prev_bfp = prev_close.avg_bfp.get(fuel)
        if parts is None:
            continue
        out[fuel] = {
            **parts,
            "total": round(total, 2),
            # The import cost in US cents a litre, this period and last, for "x% cheaper in dollars".
            "usd_cur": round(avg_bfp / fx_cur, 3),
            "usd_prev": round(prev_bfp / fx_prev, 3) if prev_bfp else None,
        }
    for fuel, leader in follows.items():
        if fuel in fuels and leader in out:
            out[fuel] = {**out[leader], "follows": leader}
    return {
        "prev_period_start": prev_start,
        "fx_prev": round(fx_prev, 4),
        "fx_cur": round(fx_cur, 4),
        "fuels": out,
    }
