"""
How sure the forecast is: the "likely range" shown next to it, and the review
period's days for the progress strip.

The range comes from CEF's own history (the reports cached in data/bfp.db). For
each recent review period that has finished, it replays the forecast from the
same stage the current one is at, with the same number of days still to come.
It takes CEF's average to that day and assumes the rest of the period stays at
that day's Basic Fuel Price, measured against the reference CEF used on each of
those days, which is what bfp_model.build_prediction does. Then it checks how far
that landed from the period's final average. The range is the forecast plus or
minus the miss that COVERAGE of those periods stayed within. Each stage is pooled
with the one either side (one day more and one fewer to come), so the range
narrows smoothly as the period fills in.

It covers the Basic Fuel Price part only. Fuel levy changes are announced ahead
and add no doubt; a slate levy change isn't known until the DMPR's announcement,
so the site says that separately.

The replay uses CEF's figures only, while the live forecast also has this tool's
estimates for days CEF hasn't published yet, so the range is a little wider than
the live forecast's real error.
"""
import datetime as dt

import bfp_model as bm

# The share of past periods the range would have caught. Checked walk-forward
# (each period's range built only from the periods before it, Mar - Oct 2026, petrol
# 95 and diesel 0.05%, every stage): 0.8 caught 78%, 0.75 only 70%. The site says
# "about 4 in 5".
COVERAGE = 0.8
PERIODS = 12      # how many of the latest finished review periods to learn from
MIN_PERIODS = 6   # fewer than this and no range is given


def finished_periods(history: list, current_start: dt.date) -> list:
    """CEF's reports grouped by review period, oldest first: each a list of reports
    in date order. Only periods before the current one whose first day is in the
    cache, so each is whole (the cache only reaches back so far)."""
    by_start = {}
    for r in history:
        if r.period_start < current_start:
            by_start.setdefault(r.period_start, []).append(r)
    periods = []
    for start in sorted(by_start):
        reports = sorted(by_start[start], key=lambda r: r.report_date)
        if reports[0].report_date == start and len(reports) >= 2:
            periods.append(reports)
    return periods


def replay_error(reports: list, fuel: str, remaining: int):
    """The miss of a forecast made with `remaining` days of the period still to come:
    projected average minus the final one, in c/l (the price change misses by the
    same amount the other way). None if the period is too short for that stage."""
    n = len(reports)
    k = n - remaining
    if k < 1:
        return None
    at, final = reports[k - 1], reports[-1]
    avg, bfp = at.avg_over_under.get(fuel), at.bfp.get(fuel)
    if avg is None or bfp is None or final.avg_over_under.get(fuel) is None:
        return None
    rest = [r.reference_price.get(fuel) for r in reports[k:]]
    if any(ref is None for ref in rest):
        return None
    projected = (avg * k + sum(ref - bfp for ref in rest)) / n
    return projected - final.avg_over_under[fuel]


def quantile(values: list, q: float) -> float:
    """The q-quantile of values, interpolating between the two nearest."""
    v = sorted(values)
    pos = (len(v) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def likely_range(history: list, current_start: dt.date, remaining: int, fuels: list,
                 follows: dict = None) -> dict:
    """The half-width of the likely range per fuel, in c/l, with what it's based on.
    A fuel in `follows` (petrol 93) gets its leader's, since its forecast is the
    leader's. half_width is empty when there's too little history."""
    follows = follows or {}
    periods = finished_periods(history, current_start)[-PERIODS:]
    half = {}
    used = 0
    if remaining <= 0:
        half = {fuel: 0.0 for fuel in fuels}
        used = len(periods)
    else:
        # The stage either side is pooled in, so the range doesn't jump about from
        # one day to the next on a dozen periods' luck.
        stages = [s for s in (remaining - 1, remaining, remaining + 1) if s >= 1]
        for fuel in fuels:
            if fuel in follows:
                continue
            errors = [abs(e) for e in (replay_error(p, fuel, s) for p in periods for s in stages) if e is not None]
            if len(errors) >= MIN_PERIODS * len(stages):
                half[fuel] = round(quantile(errors, COVERAGE), 1)
                used = max(used, len(errors) // len(stages))
        for fuel, leader in follows.items():
            if fuel in fuels and leader in half:
                half[fuel] = half[leader]
    return {
        "coverage": COVERAGE,
        "periods": used,
        "first_period": periods[0][0].period_start if periods else None,
        "last_period": periods[-1][0].period_start if periods else None,
        "remaining_days": remaining,
        "half_width": half,
    }


def review_days(period_start: dt.date, period_close: dt.date, official_through: dt.date,
                estimated: list, manual: list) -> list:
    """Every business day of the review period with where its figure comes from:
    "official" (CEF has published it), "estimated", "manual", or "to_come"."""
    est, man = set(estimated), set(manual)
    days = []
    d = period_start
    while d <= period_close:
        if bm.is_business_day(d):
            status = ("official" if d <= official_through else "manual" if d in man
                      else "estimated" if d in est else "to_come")
            days.append({"date": d, "status": status})
        d += dt.timedelta(days=1)
    return days
