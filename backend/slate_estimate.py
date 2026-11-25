"""
An estimate of the next slate levy change, before the DMPR announces it.

The slate levy recovers the slate: the running total of what petrol and diesel
have been under-recovered (negative: owed to the industry). The DMPR sets it each
month "in line with the Self-Adjusting Slate Levy Mechanism", which isn't
published, but its statements quote the slate's balance at the end of the month
two months before (end of September for the November change), and the levy has
followed that balance closely:

    levy (c/l) = RATE x (negative balance in R bn - THRESHOLD)    zero below that

THRESHOLD is the R500 million the mechanism waits for before any levy. RATE is
measured from the statements on every run (fit_rate); for the seven changes from
May to November 2026 it came out at 8.9c/l per R1 billion and the fit was within
about 3c/l of each (a levy that pays the slate back over roughly six months of
sales).

The balance the next change uses isn't published until that change is announced,
so it is rolled forward from the last published one (fuel_levy.SLATE_BALANCES)
day by day: each day's over/(under) recovery for petrol and diesel from CEF's
reports (the last report for weekends) plus the slate levy then in force, times
the litres sold a day (VOLUME). Checked against every pair of published balances
from Nov 2025 to Sep 2026, it is within R0.5 billion in calm months and out by up
to R3-4 billion in the months of the biggest swings (Mar-Jun 2026), always on the
side of a smaller debt. half_width converts those misses into c/l of levy, so the
site can show how sure the estimate is.
"""
import datetime as dt

import bfp_model as bm
import forecast_range
import fuel_levy

THRESHOLD = 0.5   # R bn: no slate levy until the negative balance passes R500 million
# Litres a day the slate covers. Roughly South Africa's petrol and diesel sales; a
# least-squares fit to the published balances gave 31-32 and 27-30 million.
VOLUME = {"petrol": 31e6, "diesel": 28e6}
GRADES = {"petrol": ("petrol95", "petrol93"), "diesel": ("diesel005", "diesel0005")}
COVERAGE = 0.8    # the share of past roll-forwards half_width would have caught
MIN_CHECKS = 5    # fewer past checks than this and no half_width is given
MAX_ROLL = 95     # days: roll forward at most about three months


def balance_month(effective: dt.date) -> dt.date:
    """The month-end whose slate balance sets the levy for a price change: the end
    of the month two months before (31 Oct for a change in December)."""
    first = effective.replace(day=1)
    return (first - dt.timedelta(days=1)).replace(day=1) - dt.timedelta(days=1)


def fit_rate(balances: list = None):
    """c/l of levy per R1 billion of negative balance above THRESHOLD, from the
    published balances and the levies they set (least squares through zero). None
    with fewer than four."""
    pts = [(-b["balance"] - THRESHOLD, fuel_levy.slate_level(b["sets"]))
           for b in (balances or fuel_levy.SLATE_BALANCES) if -b["balance"] > THRESHOLD]
    pts = [(x, y) for x, y in pts if y > 0]
    if len(pts) < 4:
        return None
    return sum(x * y for x, y in pts) / sum(x * x for x, _ in pts)


def levy_for(balance: float, rate: float) -> float:
    """The slate levy (c/l) a month-end balance (R bn) would set."""
    return round(max(0.0, rate * (-balance - THRESHOLD)), 2)


def _mean(report, grades):
    vals = [report.unit_over_under.get(g) for g in grades]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def roll(history: list, balance: float, start: dt.date, end: dt.date):
    """The slate balance (R bn) at `end`, from `balance` at `start`: each day after
    `start` up to `end` adds that day's over/(under) recovery plus the slate levy
    in force, times VOLUME. None if CEF's reports don't cover the whole stretch."""
    reports = sorted(history, key=lambda r: r.report_date)
    if not reports or reports[0].report_date > start or (end - start).days > MAX_ROLL:
        return None
    last_needed = end
    while not bm.is_business_day(last_needed):
        last_needed -= dt.timedelta(days=1)
    if reports[-1].report_date < last_needed:
        return None
    i, day = 0, start + dt.timedelta(days=1)
    while day <= end:
        while i + 1 < len(reports) and reports[i + 1].report_date <= day:
            i += 1
        report, levy = reports[i], fuel_levy.slate_level(day)
        for kind, grades in GRADES.items():
            over = _mean(report, grades)
            if over is None:
                return None
            balance += VOLUME[kind] * (over + levy) / 100 / 1e9
        day += dt.timedelta(days=1)
    return balance


def past_misses(history: list, rate: float) -> list:
    """How far the roll-forward missed each published balance from the one before
    it (up to two months apart), in c/l of levy."""
    bals = sorted(fuel_levy.SLATE_BALANCES, key=lambda b: b["at"])
    misses = []
    for a, b in zip(bals, bals[1:]):
        if (b["at"] - a["at"]).days > 62:
            continue
        rolled = roll(history, a["balance"], a["at"], b["at"])
        if rolled is not None:
            misses.append(abs(rolled - b["balance"]) * rate)
    return misses


def estimate(history: list, previous_effective: dt.date, effective: dt.date, fuels: list):
    """The estimated slate levy change on `effective` (c/l per fuel, petrol and
    diesel only), with what it's based on; None if the change is already announced
    (fuel_levy.slate_change has it) or the figures aren't there yet."""
    if fuel_levy.slate_change(previous_effective, effective, fuels):
        return None
    rate = fit_rate()
    target = balance_month(effective)
    known = [b for b in fuel_levy.SLATE_BALANCES if b["at"] <= target]
    if rate is None or not known:
        return None
    base = max(known, key=lambda b: b["at"])
    balance = base["balance"] if base["at"] == target else roll(history, base["balance"], base["at"], target)
    if balance is None:
        return None
    now = fuel_levy.slate_level(effective - dt.timedelta(days=1))
    new = levy_for(balance, rate)
    step = round(new - now, 2)
    misses = past_misses(history, rate)
    half = round(forecast_range.quantile(misses, COVERAGE), 1) if len(misses) >= MIN_CHECKS else None
    return {
        "effective": effective,
        "change": {f: step if f in fuel_levy.LEVY_FUELS else 0 for f in fuels},
        "applies": [f for f in fuels if f in fuel_levy.LEVY_FUELS],  # the fuels that carry the slate levy
        "from": now,
        "to": new,
        "balance": round(balance, 2),        # R bn, estimated, at balance_at
        "balance_at": target,
        "base_balance": base["balance"],     # the last published balance, R bn
        "base_at": base["at"],
        "rate": round(rate, 2),              # c/l per R1 bn above the threshold
        "threshold": THRESHOLD,
        "half_width": half,                  # c/l, or None
        "checks": len(misses),
    }
