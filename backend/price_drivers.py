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

Used by month_pages.py for past months (CEF's own figures). The main page had a
panel with the same split for the live forecast from 13 Nov 2026, removed the same
night at the owner's request.
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
