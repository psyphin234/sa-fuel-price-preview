"""
Builds the "preview" view on top of CEF's official daily reports:
  1. Nowcasts the day(s) since the last official CEF report using free market
     benchmarks (see market_data.py) - or uses a manual override if the user
     has entered a real Platts-based number for that day.
  2. Blends the nowcast day(s) into CEF's own official period-to-date average
     to project where the review-period average over/under recovery is heading.
  3. Translates that into an estimated next monthly pump-price move.

This is an ESTIMATE for the days CEF hasn't published yet. Every value derived
from the proxy model is tagged source="estimated" so the UI can flag it clearly,
as distinct from source="cef_official" or source="manual".
"""
import datetime as dt
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from typing import Optional

import cef_scraper as cef
import market_data as md

SA_FIXED_HOLIDAYS = {
    (1, 1): "New Year's Day",
    (3, 21): "Human Rights Day",
    (4, 27): "Freedom Day",
    (5, 1): "Workers' Day",
    (6, 16): "Youth Day",
    (8, 9): "National Women's Day",
    (9, 24): "Heritage Day",
    (12, 16): "Day of Reconciliation",
    (12, 25): "Christmas Day",
    (12, 26): "Day of Goodwill",
}


def easter_sunday(year: int) -> dt.date:
    """Anonymous Gregorian computus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


@lru_cache(maxsize=None)
def sa_public_holidays(year: int) -> dict:
    """{date: name} of South African public holidays for `year`. Under the Public
    Holidays Act a holiday falling on a Sunday moves to the Monday. One-off
    holidays the President declares (e.g. election days) aren't included."""
    holidays = {dt.date(year, m, d): name for (m, d), name in SA_FIXED_HOLIDAYS.items()}
    easter = easter_sunday(year)
    holidays[easter - dt.timedelta(days=2)] = "Good Friday"
    holidays[easter + dt.timedelta(days=1)] = "Family Day"
    for d, name in list(holidays.items()):
        if d.weekday() == 6:
            monday = d + dt.timedelta(days=1)
            holidays.setdefault(monday, f"{name} (observed)")
    return holidays


def holiday_name(d: dt.date) -> Optional[str]:
    return sa_public_holidays(d.year).get(d)


def is_business_day(d: dt.date) -> bool:
    return d.weekday() < 5 and holiday_name(d) is None


def business_days_between(start: dt.date, end: dt.date) -> int:
    """Inclusive count of business days from start to end."""
    n = 0
    d = start
    while d <= end:
        if is_business_day(d):
            n += 1
        d += dt.timedelta(days=1)
    return n


def first_wednesday(year: int, month: int) -> dt.date:
    d = dt.date(year, month, 1)
    return d + dt.timedelta(days=(2 - d.weekday()) % 7)  # Wednesday = weekday 2


def next_price_change_date(pump_price_effective: dt.date) -> dt.date:
    """SA fuel prices change on the first Wednesday of each month (verified
    against every 2026 DMRE announcement so far - Jan 7, Mar 4, Apr 1, May 6,
    Jun 3, Jul 1, Aug 5). The *exact* day the underlying review data stops
    being updated isn't a fixed calendar date (it shifts a little with the
    Mediterranean trading calendar), so we count down to this known,
    government-set date instead of guessing that one."""
    year, month = pump_price_effective.year, pump_price_effective.month + 1
    if month > 12:
        month = 1
        year += 1
    return first_wednesday(year, month)


def business_days_after(after: dt.date, through: dt.date) -> list:
    """List of business days strictly after `after`, up to and including `through`."""
    days = []
    d = after + dt.timedelta(days=1)
    while d <= through:
        if is_business_day(d):
            days.append(d)
        d += dt.timedelta(days=1)
    return days


@dataclass
class DayEstimate:
    date: dt.date
    source: str  # "cef_official" | "estimated" | "manual"
    bfp: dict
    unit_over_under: dict
    exchange_rate: Optional[float] = None
    note: Optional[str] = None


def build_daily_moves(benchmarks: dict, recorded: dict) -> dict:
    """{benchmark name: {trading date: day-over-day % move}}. Moves recorded live
    from Yahoo's own change figure (see db.upsert_benchmark_day) are roll-safe and
    win; raw close-to-close from the price history only fills days we never saw."""
    moves = {}
    for name, bench in benchmarks.items():
        history = sorted((bench.get("history") or {}).items())
        day_moves = {
            d: (close / prev - 1)
            for (_, prev), (d, close) in zip(history, history[1:])
            if prev
        }
        day_moves.update(recorded.get(name, {}))
        moves[name] = day_moves
    return moves


def _move_factor(day_moves: dict, after: dt.date, through: dt.date) -> float:
    factor = 1.0
    for d, pct in day_moves.items():
        if after < d <= through:
            factor *= 1 + pct
    return factor


def nowcast_single_day(base: cef.DailyReport, target_date: dt.date, moves: dict) -> DayEstimate:
    """Estimate one day's BFP from the last official report by compounding each
    benchmark's daily moves from the day after that report up to and including
    `target_date`. A finished day's moves are final, so its estimate stops
    changing; only today's keeps tracking live prices."""
    fx_factor = _move_factor(moves.get("usdzar", {}), base.report_date, target_date)

    bfp_est, unit_est = {}, {}
    for fuel in cef.FUELS:
        base_bfp = base.bfp.get(fuel)
        ref = base.reference_price.get(fuel)
        if base_bfp is None:
            continue
        prod_factor = _move_factor(moves.get(md.FUEL_PROXY[fuel], {}), base.report_date, target_date)
        est_bfp = base_bfp * prod_factor * fx_factor
        bfp_est[fuel] = round(est_bfp, 3)
        if ref is not None:
            unit_est[fuel] = round(ref - est_bfp, 3)

    return DayEstimate(
        date=target_date,
        source="estimated",
        bfp=bfp_est,
        unit_over_under=unit_est,
        exchange_rate=round(base.exchange_rate * fx_factor, 4) if base.exchange_rate else None,
        note="Estimated from free market benchmarks (Brent/RBOB/ULSD futures + USD/ZAR), "
             "not the real Platts Mediterranean assessment. Replace with a manual entry if you "
             "have an actual Platts-based figure for this day.",
    )


@dataclass
class Prediction:
    fuel: str
    label: str
    official_avg_over_under: float
    official_days_count: int
    blended_avg_over_under: float
    blended_days_count: int
    estimated_days: list
    manual_days: list
    predicted_pump_price_change_c_per_l: float
    current_price_c_per_l: Optional[float]
    predicted_new_price_c_per_l: Optional[float]
    direction: str
    note: str


def build_prediction(fuel: str, latest: cef.DailyReport, moves: dict,
                      manual_overrides: dict = None, today: dt.date = None) -> Prediction:
    """manual_overrides: {date: {"bfp": {...}, "exchange_rate": ...}} - real numbers the user typed in,
    which take priority over the estimated nowcast for that date."""
    manual_overrides = manual_overrides or {}
    today = today or dt.date.today()

    official_avg = latest.avg_over_under.get(fuel)
    official_days = business_days_between(latest.period_start, latest.period_end)

    gap_days = business_days_after(latest.report_date, today)

    day_values = []
    for d in gap_days:
        if d in manual_overrides and "bfp" in manual_overrides[d] and fuel in manual_overrides[d]["bfp"]:
            mo = manual_overrides[d]
            bfp_val = mo["bfp"][fuel]
            ref = latest.reference_price.get(fuel)
            day_values.append(DayEstimate(
                date=d, source="manual", bfp={fuel: bfp_val},
                unit_over_under={fuel: round(ref - bfp_val, 3)} if ref is not None else {},
                exchange_rate=mo.get("exchange_rate"),
                note="Manually entered value.",
            ))
        else:
            day_values.append(nowcast_single_day(latest, d, moves))

    n_new = len(day_values)
    new_sum = sum(dv.unit_over_under.get(fuel, 0) for dv in day_values if fuel in dv.unit_over_under)
    blended_days = official_days + n_new
    blended_avg = ((official_avg * official_days) + new_sum) / blended_days if blended_days else official_avg

    direction = "increase" if blended_avg < 0 else ("decrease" if blended_avg > 0 else "no change")
    predicted_change = -blended_avg  # under-recovery (negative) -> price must rise to recover it

    current_price = latest.current_price.get(fuel)
    predicted_new_price = (current_price + predicted_change) if current_price is not None else None

    return Prediction(
        fuel=fuel,
        label=cef.FUEL_LABELS[fuel],
        official_avg_over_under=round(official_avg, 3) if official_avg is not None else None,
        official_days_count=official_days,
        blended_avg_over_under=round(blended_avg, 3),
        blended_days_count=blended_days,
        estimated_days=[asdict(dv) for dv in day_values if dv.source == "estimated"],
        manual_days=[asdict(dv) for dv in day_values if dv.source == "manual"],
        predicted_pump_price_change_c_per_l=round(predicted_change, 2),
        current_price_c_per_l=current_price,
        predicted_new_price_c_per_l=round(predicted_new_price, 2) if predicted_new_price is not None else None,
        direction=direction,
        note="Based on CEF's official review-period average so far, plus this tool's estimate for "
             f"{n_new} day(s) not yet published by CEF. The review period only closes around the "
             "25th of the month, and the final government-announced price also reflects separate "
             "slate-levy/fuel-levy decisions, so treat this as a directional estimate, not a guarantee.",
    )
