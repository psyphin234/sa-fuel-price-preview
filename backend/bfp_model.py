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
import market_data as md

SA_HOLIDAYS_2026 = {
    dt.date(2026, 1, 1), dt.date(2026, 3, 21), dt.date(2026, 4, 3),
    dt.date(2026, 4, 6), dt.date(2026, 4, 27), dt.date(2026, 5, 1),
    dt.date(2026, 6, 16), dt.date(2026, 8, 9), dt.date(2026, 8, 10),
    dt.date(2026, 9, 24), dt.date(2026, 12, 16), dt.date(2026, 12, 25),
    dt.date(2026, 12, 26),
}


def is_business_day(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in SA_HOLIDAYS_2026


def business_days_between(start: dt.date, end: dt.date) -> int:
    """Inclusive count of business days from start to end."""
    n = 0
    d = start
    while d <= end:
        if is_business_day(d):
            n += 1
        d += dt.timedelta(days=1)
    return n


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


def nowcast_single_day(base: cef.DailyReport, target_date: dt.date, benchmarks: dict) -> DayEstimate:
    """Estimate one day's BFP by applying the % move in free benchmarks (vs the
    previous close) to the last official BFP for each fuel, and today's live
    USD/ZAR rate vs the last official exchange rate."""
    fx = benchmarks.get("usdzar", {})
    fx_price = fx.get("price")
    fx_pct = fx.get("pct_change", 0.0) or 0.0

    bfp_est, unit_est = {}, {}
    for fuel in cef.FUELS:
        proxy_name = md.FUEL_PROXY[fuel]
        proxy = benchmarks.get(proxy_name, {})
        prod_pct = proxy.get("pct_change", 0.0) or 0.0
        base_bfp = base.bfp.get(fuel)
        ref = base.reference_price.get(fuel)
        if base_bfp is None:
            continue
        est_bfp = base_bfp * (1 + prod_pct) * (1 + fx_pct)
        bfp_est[fuel] = round(est_bfp, 3)
        if ref is not None:
            unit_est[fuel] = round(ref - est_bfp, 3)

    return DayEstimate(
        date=target_date,
        source="estimated",
        bfp=bfp_est,
        unit_over_under=unit_est,
        exchange_rate=round(fx_price, 4) if fx_price else None,
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


def build_prediction(fuel: str, latest: cef.DailyReport, benchmarks: dict,
                      manual_overrides: dict = None, today: dt.date = None) -> Prediction:
    """manual_overrides: {date: {"bfp": {...}, "exchange_rate": ...}} - real numbers the user typed in,
    which take priority over the estimated nowcast for that date."""
    manual_overrides = manual_overrides or {}
    today = today or dt.date.today()

    official_avg = latest.avg_over_under.get(fuel)
    official_days = business_days_between(latest.period_start, latest.period_end)

    gap_days = business_days_after(latest.report_date, today)

    day_values = []
    running_base = latest
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
            est = nowcast_single_day(running_base, d, benchmarks)
            day_values.append(est)
            # chain subsequent estimated days off this one so a multi-day gap compounds sensibly
            if est.bfp.get(fuel) is not None:
                chained = cef.DailyReport(
                    report_date=d, period_start=latest.period_start, period_end=latest.period_end,
                    reference_valid_from=latest.reference_valid_from,
                    pump_price_effective=latest.pump_price_effective,
                    reference_price=latest.reference_price, bfp=est.bfp,
                    unit_over_under=est.unit_over_under, exchange_rate=est.exchange_rate,
                )
                running_base = chained

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
