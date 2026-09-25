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
from typing import Optional

import cef_scraper as cef
import nowcast

def is_business_day(d: dt.date) -> bool:
    """A day CEF publishes a daily BFP report for. Checked against Jun 2025 - Sep
    2026: CEF publishes every weekday, public holidays included (on days with no
    London Platts assessment, e.g. Christmas, it repeats the previous figure)."""
    return d.weekday() < 5


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


def nowcast_single_day(base: cef.DailyReport, target_date: dt.date, market: dict, weights: dict) -> DayEstimate:
    """Estimate one day's BFP from the last official report (see nowcast.py)."""
    bfp_est, fx_est = nowcast.estimate(base, target_date, market, weights, cef.FUELS)
    unit_est = {
        fuel: round(base.reference_price[fuel] - v, 3)
        for fuel, v in bfp_est.items()
        if base.reference_price.get(fuel) is not None
    }
    return DayEstimate(
        date=target_date,
        source="estimated",
        bfp=bfp_est,
        unit_over_under=unit_est,
        exchange_rate=fx_est,
        note="Estimated from US petrol, diesel and Brent futures plus USD/ZAR, weighted by how "
             "CEF's own figures have tracked them - not the real Platts Mediterranean assessment.",
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


def build_prediction(fuel: str, latest: cef.DailyReport, market: dict, weights: dict,
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
            day_values.append(nowcast_single_day(latest, d, market, weights))

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
