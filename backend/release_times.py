"""
Prints when CEF's daily reports became available, from the local release log
(see db.note_report_missing / note_report_found), to help pick a tighter
schedule for the publish job.

Each release is known to fall between the last check that found it missing and
the first check that found it. Only tight windows (<= MAX_WINDOW_MINUTES, i.e.
consecutive hourly checks) count towards the average; wider ones - the PC was
off, or the report was only backfilled - are listed but ignored.

Usage:  python release_times.py
"""
import datetime as dt
import statistics

import db

MAX_WINDOW_MINUTES = 90


def minutes_of_day(t: dt.datetime) -> float:
    return t.hour * 60 + t.minute + t.second / 60


def hhmm(minutes: float) -> str:
    minutes = round(minutes)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def main():
    db.init_db()
    rows = db.get_release_log()
    if not rows:
        print("No releases logged yet - check back after the hourly job has run for a few days.")
        return

    midpoints = []
    print(f"{'Report date':<12} {'Released between':<36} {'Window':>7}  Used")
    for r in rows:
        found = dt.datetime.fromisoformat(r["first_seen_at"])
        missing = dt.datetime.fromisoformat(r["last_missing_at"]) if r["last_missing_at"] else None
        if missing is None or missing >= found:
            print(f"{r['report_date']:<12} {'? and ' + found.strftime('%a %d %b %H:%M'):<36} {'-':>7}  no (never seen missing)")
            continue
        window = (found - missing).total_seconds() / 60
        used = window <= MAX_WINDOW_MINUTES and missing.date() == found.date()
        span = f"{missing.strftime('%a %d %b %H:%M')} and {found.strftime('%H:%M')}"
        print(f"{r['report_date']:<12} {span:<36} {round(window):>5}m  {'yes' if used else 'no (window too wide)'}")
        if used:
            midpoints.append((minutes_of_day(missing) + minutes_of_day(found)) / 2)

    print()
    if not midpoints:
        print("No tight release windows yet, so no average.")
        return
    print(f"Tight windows: {len(midpoints)}")
    print(f"Average release time: ~{hhmm(statistics.mean(midpoints))}")
    print(f"Median release time:  ~{hhmm(statistics.median(midpoints))}")
    print(f"Earliest / latest:    ~{hhmm(min(midpoints))} / ~{hhmm(max(midpoints))}")


if __name__ == "__main__":
    main()
