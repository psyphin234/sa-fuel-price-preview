"""
Tracks how close this tool's estimated days turn out to be once CEF publishes
the real official BFP for that date, so the UI can show an empirical accuracy
meter instead of an unverified claim.

Flow: every time a day is estimated (bfp_model.build_prediction's
estimated_days), we remember that guess. The next time CEF publishes the
official figure for that same date, we compare the two, log the error, and
forget the pending guess. Manual entries are never scored here - they're your
own real numbers, not this tool's guess.
"""
import datetime as dt

import db
import cef_scraper as cef


def log_estimates(predictions: dict):
    """predictions: {fuel: bfp_model.Prediction}."""
    for fuel, pred in predictions.items():
        for day in pred.estimated_days:
            date = day["date"]
            if isinstance(date, str):
                date = dt.date.fromisoformat(date)
            bfp_val = day["bfp"].get(fuel)
            if bfp_val is not None:
                db.upsert_estimate(date, fuel, bfp_val)


def reconcile(period_reports: list):
    """period_reports: list of cef.DailyReport already officially published.
    Idempotent - once a (date, fuel) pair is reconciled its pending estimate
    is deleted, so re-running this on the same data is a no-op."""
    for report in period_reports:
        for fuel in cef.FUELS:
            official = report.bfp.get(fuel)
            if official is None:
                continue
            estimated = db.pop_estimate(report.report_date, fuel)
            if estimated is not None:
                db.log_accuracy(report.report_date, fuel, estimated, official)


READY_THRESHOLD = 5  # comparisons needed before we call the average trustworthy


def get_accuracy_summary(limit: int = 90) -> dict:
    records = db.get_accuracy_records(limit=limit)
    n = len(records)
    if n == 0:
        return {
            "n": 0,
            "mean_abs_pct_error": None,
            "mean_abs_error_c_per_l": None,
            "accuracy_pct": None,
            "status": "collecting",
        }

    abs_pct_errors = [abs(r["pct_error"]) for r in records if r["pct_error"] is not None]
    abs_errors = [abs(r["error_c_per_l"]) for r in records]
    mean_abs_pct = (sum(abs_pct_errors) / len(abs_pct_errors)) if abs_pct_errors else None
    mean_abs_err = sum(abs_errors) / len(abs_errors)
    accuracy_pct = max(0.0, min(100.0, 100.0 - mean_abs_pct * 100)) if mean_abs_pct is not None else None

    return {
        "n": n,
        "mean_abs_pct_error": round(mean_abs_pct * 100, 2) if mean_abs_pct is not None else None,
        "mean_abs_error_c_per_l": round(mean_abs_err, 2),
        "accuracy_pct": round(accuracy_pct, 1) if accuracy_pct is not None else None,
        "status": "ready" if n >= READY_THRESHOLD else "warming_up",
    }
