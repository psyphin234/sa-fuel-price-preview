"""
Standalone script - no Flask, no listening socket - that computes the same
data the local dashboard's /api/status endpoint serves, writes it to
docs/data/status.json, and pushes it to GitHub so the public GitHub Pages
site can pick it up.

Run this on a schedule (Windows Task Scheduler). It only ever makes OUTBOUND
connections (to cefgroup.co.za, Yahoo Finance, and github.com) - it never
opens a port or accepts a connection, so nothing about this machine is
discoverable from the published site or its repo.
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import app as backend
import cef_scraper as cef
import bfp_model as bm

REPO_ROOT = Path(__file__).parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "data" / "status.json"


def build_status() -> dict:
    latest = backend.get_latest_report()
    if latest is None:
        raise RuntimeError("Could not reach CEF's site or parse any recent report.")

    benchmarks = backend.get_benchmarks(force=True)
    overrides = backend.manual_overrides_dict()
    today = dt.date.today()

    predictions = {}
    for fuel in cef.FUELS:
        predictions[fuel] = bm.build_prediction(fuel, latest, benchmarks, manual_overrides=overrides, today=today)

    period_reports = backend.get_period_reports(latest.period_start, latest.period_end)
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
    for fuel in cef.FUELS:
        for day in predictions[fuel].estimated_days + predictions[fuel].manual_days:
            daily_series[fuel].append({
                "date": day["date"],
                "bfp": day["bfp"].get(fuel),
                "unit_over_under": day["unit_over_under"].get(fuel),
                "source": day["source"],
            })

    return {
        "latest_official_report": latest,
        "fuels": cef.FUEL_LABELS,
        "predictions": predictions,
        "daily_series": daily_series,
        "generated_at": dt.datetime.now(),
    }


def write_json(data: dict):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, default=backend.json_default, indent=2)


def run_git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)


def git_publish():
    add = run_git("add", "docs/data/status.json")
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {add.stderr.strip()}")

    status = run_git("status", "--porcelain", "docs/data/status.json")
    if status.returncode != 0:
        raise RuntimeError(f"git status failed: {status.stderr.strip()}")
    if not status.stdout.strip():
        print("No changes to publish (data is unchanged since last run).")
        return

    stamp = dt.datetime.now().isoformat(timespec="seconds")
    commit = run_git("commit", "-m", f"Update BFP preview data ({stamp})")
    if commit.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit.stderr.strip()}")
    print(commit.stdout.strip())

    push = run_git("push")
    if push.returncode != 0:
        raise RuntimeError(f"git push failed: {push.stderr.strip()}")
    print("Pushed to GitHub.")


if __name__ == "__main__":
    try:
        data = build_status()
        write_json(data)
        print(f"Wrote {OUTPUT_PATH}")
        git_publish()
    except Exception as e:
        print(f"publish.py failed: {e}", file=sys.stderr)
        sys.exit(1)
