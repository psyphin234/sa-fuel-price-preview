"""
Backtests ways of estimating CEF's next daily Basic Fuel Price from free market
data, using CEF's own published history (backtest_fetch.py) and Yahoo hourly
prices (data/backtest/market.json).

Each candidate estimates day D from the previous official report P, exactly as
the live site does. Fitted models only ever learn from days before D
(walk-forward), so the scores are honest out-of-sample numbers.

Usage:  python backtest.py
"""
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

DATA = Path(__file__).parent.parent / "data" / "backtest"
FUELS = ["petrol95", "petrol93", "diesel005", "diesel0005", "illpar"]
PROXY = {"petrol95": "rbob", "petrol93": "rbob", "diesel005": "ho", "diesel0005": "ho", "illpar": "ho"}
LONDON_HOURS = list(range(8, 23))
TRAIN_WINDOW = 60
MIN_TRAIN = 30


# ---------- time helpers ----------
def last_sunday(year, month):
    d = dt.date(year + month // 12, month % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def london_offset_hours(utc: dt.datetime) -> int:
    start = dt.datetime.combine(last_sunday(utc.year, 3), dt.time(1))
    end = dt.datetime.combine(last_sunday(utc.year, 10), dt.time(1))
    return 1 if start <= utc < end else 0


def london_to_utc(day: dt.date, hour: int) -> dt.datetime:
    naive = dt.datetime.combine(day, dt.time(hour))
    return naive - dt.timedelta(hours=london_offset_hours(naive))


# ---------- market data ----------
class Series:
    """Hourly bars with futures-roll gaps removed. `adj` is a cumulative log price
    whose differences are true price moves of one contract."""

    def __init__(self, bars, name, detect_rolls=True):
        bars = sorted((b for b in bars if b[1] is not None and b[2] is not None), key=lambda b: b[0])
        self.times = np.array([b[0] for b in bars], dtype=np.int64)
        opens = np.array([b[1] for b in bars], dtype=float)
        closes = np.array([b[2] for b in bars], dtype=float)
        self.raw_close = closes
        gaps = np.zeros(len(bars))
        gaps[1:] = np.log(opens[1:] / closes[:-1])
        body = np.log(closes / opens)
        self.rolls = []
        if detect_rolls:
            by_month = defaultdict(list)
            for i in range(1, len(bars)):
                t = dt.datetime.utcfromtimestamp(int(self.times[i]))
                by_month[(t.year, t.month)].append((i, t))
            for key, items in by_month.items():
                typical = np.median([abs(gaps[i]) for i, _ in items]) or 1e-6
                cand = [(abs(gaps[i]), i, t) for i, t in items if t.day >= 12]
                if not cand:
                    continue
                size, i, t = max(cand)
                if size > 0.004 and size > 8 * typical:
                    self.rolls.append((t.date(), float(gaps[i])))
                    gaps[i] = 0.0
        self.adj = np.cumsum(gaps + body)
        self.name = name

    def at(self, when_utc: dt.datetime):
        """Adjusted log price at the close of the last bar ending at or before when_utc."""
        ts = when_utc.replace(tzinfo=dt.timezone.utc).timestamp() - 3600
        i = np.searchsorted(self.times, ts, side="right") - 1
        if i < 0:
            return None
        # stale if the last bar is more than 3 days old
        if ts - self.times[i] > 3 * 86400:
            return None
        return self.adj[i]

    def raw_at(self, when_utc: dt.datetime):
        ts = when_utc.replace(tzinfo=dt.timezone.utc).timestamp() - 3600
        i = np.searchsorted(self.times, ts, side="right") - 1
        return None if i < 0 else self.raw_close[i]


def load_market():
    m = json.loads((DATA / "market.json").read_text())
    # roll-gap removal tested worse (1.367% vs 1.346%), so it's off
    return {name: Series(m[f"{name}_1h"]["bars"], name, detect_rolls=False)
            for name in ("rbob", "ho", "brent", "wti", "usdzar")}


# ---------- CEF data ----------
def load_cef():
    raw = json.loads((DATA / "cef_reports.json").read_text())
    reports = {}
    for d, r in raw.items():
        if "missing" in r or not r.get("bfp") or not r.get("exchange_rate"):
            continue
        if any(r["bfp"].get(f) is None for f in FUELS):
            continue
        reports[dt.date.fromisoformat(d)] = r
    return reports, raw


# ---------- analysis ----------
def calendar_report(raw):
    missing = sorted(dt.date.fromisoformat(d) for d, r in raw.items()
                     if "missing" in r and dt.date.fromisoformat(d).weekday() < 5)
    print(f"\n=== Weekdays with no CEF report ({len(missing)}) ===")
    for d in missing:
        print(f"  {d} {d.strftime('%a')}  {raw[d.isoformat()]['missing']}")
    weekend_reports = [d for d, r in raw.items() if "missing" not in r and dt.date.fromisoformat(d).weekday() >= 5]
    print("  Weekend reports:", weekend_reports or "none")
    next_folder = [d for d, r in raw.items() if "missing" not in r and f"/{d[5:7]}/Daily" not in r.get("url", "")]
    print(f"  Reports only found in the NEXT month's upload folder: {len(next_folder)} e.g. {sorted(next_folder)[:6]}")


def fx_fixing(reports, mk):
    print("\n=== CEF exchange rate vs Yahoo USD/ZAR by London hour (mean abs % diff) ===")
    zar = mk["usdzar"]
    best = None
    for h in LONDON_HOURS:
        diffs = []
        for d, r in reports.items():
            y = zar.raw_at(london_to_utc(d, h))
            if y:
                diffs.append(abs(r["exchange_rate"] / y - 1))
        score = np.mean(diffs) * 100
        print(f"  {h:02d}:00  {score:.3f}%  (n={len(diffs)})")
        if best is None or score < best[1]:
            best = (h, score)
    print(f"  -> best match {best[0]:02d}:00 London")
    return best[0]


def evaluate(reports, mk, fx_hour):
    days = sorted(reports)
    pairs = [(p, d) for p, d in zip(days, days[1:]) if (d - p).days <= 5]

    def usd(r, f):
        return r["bfp"][f] / r["exchange_rate"]

    def fx_est(p, d):
        zp, zd = mk["usdzar"].raw_at(london_to_utc(p, fx_hour)), mk["usdzar"].raw_at(london_to_utc(d, fx_hour))
        return reports[p]["exchange_rate"] * zd / zp if zp and zd else None

    def move(name, p, d, h, lag=0):
        a = mk[name].at(london_to_utc(p - dt.timedelta(days=lag), h))
        b = mk[name].at(london_to_utc(d - dt.timedelta(days=lag), h))
        return None if a is None or b is None else b - a

    # target and features per (pair, fuel)
    results = defaultdict(lambda: defaultdict(list))  # model -> fuel -> abs errors (c/l)
    pct_results = defaultdict(lambda: defaultdict(list))  # model -> fuel -> abs % errors
    daily = defaultdict(dict)  # (date, fuel) -> {model: estimate}
    fx_errors = []
    history = defaultdict(list)  # fuel -> list of (features dict, target log usd move) in time order

    ny_close_hour = 21  # ~16:00-17:00 New York in London time
    for p, d in pairs:
        rp, rd = reports[p], reports[d]
        fxe = fx_est(p, d)
        if fxe is None:
            continue
        fx_errors.append(abs(fxe / rd["exchange_rate"] - 1))
        feats_all = {}
        for h in LONDON_HOURS:
            for name in ("rbob", "ho", "brent", "wti"):
                feats_all[(name, h, 0)] = move(name, p, d, h)
                feats_all[(name, h, 1)] = move(name, p, d, h, lag=1)
        for f in FUELS:
            actual = rd["bfp"][f]
            y = math.log(usd(rd, f) / usd(rp, f))
            feats = dict(feats_all)
            prev = history[f][-1] if history[f] else None
            if prev is not None:
                pf, py = prev
                base = pf.get((PROXY[f], 15, 0))
                feats[("resid", 0, 0)] = py - base if base is not None else None
                feats[("prevmove", 0, 0)] = py

            scored = len(history[f]) >= MIN_TRAIN

            def record(model, est):
                if scored and est is not None and math.isfinite(est):
                    results[model][f].append(abs(est - actual))
                    pct_results[model][f].append(abs(est / actual - 1) * 100)
                    daily[(d, f)][model] = est

            # baselines
            record("A. no change (tomorrow = today)", rp["bfp"][f])
            record("B. no change in USD, FX updated", usd(rp, f) * fxe)
            # current live-style model: NY close % move of the fuel's proxy x FX move
            m = feats_all.get((PROXY[f], ny_close_hour, 0))
            if m is not None:
                record("C. current site model (NY close, 1:1)", usd(rp, f) * math.exp(m) * fxe)
            # single-proxy 1:1 at each London hour
            for h in LONDON_HOURS:
                m = feats_all.get((PROXY[f], h, 0))
                if m is not None:
                    record(f"D. proxy 1:1 at {h:02d}:00 London", usd(rp, f) * math.exp(m) * fxe)
            # walk-forward fitted models
            for window in (30, 60, 120, 250):
              hist = history[f][-window:]
              if len(hist) < MIN_TRAIN:
                  continue
              for label, keys in fitted_models(f, window).items():
                    X = np.array([[hf[k] for k in keys] for hf, _ in hist if all(hf.get(k) is not None for k in keys)])
                    Y = np.array([yy for hf, yy in hist if all(hf.get(k) is not None for k in keys)])
                    x = [feats.get(k) for k in keys]
                    if len(Y) < MIN_TRAIN or any(v is None for v in x):
                        continue
                    beta = ridge(X, Y)
                    record(label, usd(rp, f) * math.exp(float(np.dot(beta, x))) * fxe)
            history[f].append((feats, y))

    return (results, pct_results, daily), fx_errors, pairs


def fitted_models(fuel, window):
    models = {}
    for h in (14, 15, 16, 17):
        core = [("rbob", h, 0), ("ho", h, 0), ("brent", h, 0)]
        if window == 60:
            models[f"E. fitted proxy only @{h}"] = [(PROXY[fuel], h, 0)]
            models[f"G. F + previous-day moves @{h}"] = core + [("rbob", h, 1), ("ho", h, 1), ("brent", h, 1)]
            models[f"H. F + yesterday's miss @{h}"] = core + [("resid", 0, 0)]
            models[f"I. F + wti @{h}"] = core + [("wti", h, 0)]
        models[f"F. fitted rbob+ho+brent @{h} win{window}"] = core
    return models


def ridge(X, Y, lam=1e-5):
    """No intercept: a flat market should mean a flat BFP."""
    return np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ Y)


def main():
    reports, raw = load_cef()
    mk = load_market()
    print(f"CEF reports: {len(reports)}  ({min(reports)} -> {max(reports)})")
    for name in ("rbob", "ho", "brent", "wti"):
        rolls = [(str(d), round(g * 100, 2)) for d, g in mk[name].rolls if d >= min(reports) - dt.timedelta(days=40)]
        print(f"  {name} roll gaps removed (date, %): {rolls}")
    calendar_report(raw)
    fx_hour = fx_fixing(reports, mk)
    results, fx_errors, pairs = evaluate(reports, mk, fx_hour)
    global LAST
    LAST = (results, pairs)
    print(f"\n  FX estimate error (from {fx_hour:02d}:00 London rate): mean {np.mean(fx_errors)*100:.3f}%")

    print(f"\n=== 1-day-ahead estimate error, mean absolute c/l (n={len(pairs)} day pairs) ===")
    results, pct_results, daily = results
    rows = []
    for model, per_fuel in pct_results.items():
        allerr = [e for f in FUELS for e in per_fuel[f]]
        allc = [e for f in FUELS for e in results[model][f]]
        rows.append((np.mean(allerr), model, {f: np.mean(per_fuel[f]) for f in FUELS}, np.mean(allc), len(per_fuel["petrol95"])))
    rows.sort()
    print("  (mean absolute % error per fuel; 'c/l' = mean absolute error in cents/litre across fuels)")
    print(f"  {'model':<40} {'all %':>6} " + " ".join(f"{f[:9]:>9}" for f in FUELS) + "    c/l    n")
    shown = [r for r in rows[:15]] + [r for r in rows if r[1][0] in "ABC"]
    for avg, model, pf, cl, n in shown:
        print(f"  {model:<40} {avg:6.3f} " + " ".join(f"{pf[f]:9.3f}" for f in FUELS) + f"  {cl:6.2f} {n:4d}")
    return rows, daily


if __name__ == "__main__":
    main()
