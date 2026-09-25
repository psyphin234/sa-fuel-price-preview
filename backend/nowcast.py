"""
Estimates CEF's Basic Fuel Price for days it hasn't published yet.

Chosen by backtesting against CEF's own history (backtest.py, Jun 2025 - Sep 2026,
~300 day-ahead estimates per fuel):

  - Each fuel's BFP is split into its US-dollar part (BFP / CEF exchange rate) and
    the exchange rate.
  - The dollar part moves with a per-fuel weighted mix of US petrol (RBOB), diesel
    (heating oil) and Brent futures, read at 15:00 London - just before Platts'
    16:30 London assessment window that CEF's figures are built from. The weights
    are re-fitted every run on up to the last 250 CEF days (ridge regression, no
    intercept), because they drift over time.
  - CEF's exchange rate tracks Yahoo's USD/ZAR at 10:00 London most closely.

Backtest mean absolute error: 1.35% vs 2.04% for "no change" and 2.11% for the
previous model (proxy % move at the New York close).
"""
import datetime as dt
import math

import numpy as np
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BFP-preview-tool/1.0"}
YF_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

FEATURES = {"rbob": "RB=F", "ho": "HO=F", "brent": "BZ=F"}
FX_SYMBOL = "ZAR=X"
PRODUCT_HOUR_LONDON = 15
FX_HOUR_LONDON = 10
TRAIN_WINDOW = 250
MIN_TRAIN = 30
MAX_PAIR_GAP_DAYS = 5


def _last_sunday(year: int, month: int) -> dt.date:
    d = dt.date(year + month // 12, month % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def london_to_utc(day: dt.date, hour: int) -> dt.datetime:
    naive = dt.datetime.combine(day, dt.time(hour))
    bst = (dt.datetime.combine(_last_sunday(day.year, 3), dt.time(1)) <= naive
           < dt.datetime.combine(_last_sunday(day.year, 10), dt.time(1)))
    return naive - dt.timedelta(hours=1 if bst else 0)


class HourlySeries:
    """Hourly closes; `at` returns the last close at or before a moment (so a
    snapshot time that hasn't happened yet gives the latest live price)."""

    def __init__(self, bars):
        bars = sorted((t, c) for t, c in bars if c is not None)
        self.times = np.array([t for t, _ in bars], dtype=np.int64)
        self.closes = np.array([c for _, c in bars], dtype=float)

    def at(self, when_utc: dt.datetime):
        # a bar's close is known one hour after its start
        ts = when_utc.replace(tzinfo=dt.timezone.utc).timestamp() - 3600
        i = int(np.searchsorted(self.times, ts, side="right")) - 1
        if i < 0 or ts - self.times[i] > 4 * 86400:
            return None
        return float(self.closes[i])


def fetch_hourly(symbol: str, range_: str = "2y") -> HourlySeries:
    resp = requests.get(YF_CHART_URL.format(symbol=symbol), headers=HEADERS,
                        params={"range": range_, "interval": "1h"}, timeout=30)
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    return HourlySeries(zip(result["timestamp"], result["indicators"]["quote"][0]["close"]))


def fetch_market() -> dict:
    """{name: HourlySeries} for the model's inputs plus "usdzar". Missing on failure."""
    market = {}
    for name, symbol in {**FEATURES, "usdzar": FX_SYMBOL}.items():
        try:
            market[name] = fetch_hourly(symbol)
        except Exception:
            pass
    return market


def _log_move(series: HourlySeries, a: dt.datetime, b: dt.datetime):
    pa, pb = series.at(a), series.at(b)
    return math.log(pb / pa) if pa and pb else None


def product_features(market: dict, from_day: dt.date, to_day: dt.date):
    if not all(name in market for name in FEATURES):
        return None
    a, b = london_to_utc(from_day, PRODUCT_HOUR_LONDON), london_to_utc(to_day, PRODUCT_HOUR_LONDON)
    moves = [_log_move(market[name], a, b) for name in FEATURES]
    return None if any(m is None for m in moves) else moves


def fx_ratio(market: dict, from_day: dt.date, to_day: dt.date):
    if "usdzar" not in market:
        return None
    a, b = london_to_utc(from_day, FX_HOUR_LONDON), london_to_utc(to_day, FX_HOUR_LONDON)
    move = _log_move(market["usdzar"], a, b)
    return math.exp(move) if move is not None else None


def fit_weights(history: list, market: dict, fuels: list) -> dict:
    """history: official reports (objects with report_date, bfp, exchange_rate) in date
    order. Returns {fuel: weights array} fitted on consecutive-report pairs."""
    pairs = [(p, d) for p, d in zip(history, history[1:])
             if (d.report_date - p.report_date).days <= MAX_PAIR_GAP_DAYS and p.exchange_rate and d.exchange_rate]
    pairs = pairs[-TRAIN_WINDOW:]
    rows = []
    for p, d in pairs:
        x = product_features(market, p.report_date, d.report_date)
        if x is not None:
            rows.append((x, p, d))
    weights = {}
    for fuel in fuels:
        X, Y = [], []
        for x, p, d in rows:
            bp, bd = p.bfp.get(fuel), d.bfp.get(fuel)
            if bp and bd:
                X.append(x)
                Y.append(math.log((bd / d.exchange_rate) / (bp / p.exchange_rate)))
        if len(Y) >= MIN_TRAIN:
            X, Y = np.array(X), np.array(Y)
            weights[fuel] = np.linalg.solve(X.T @ X + 1e-5 * np.eye(X.shape[1]), X.T @ Y)
    return weights


def estimate(base, target_day: dt.date, market: dict, weights: dict, fuels: list):
    """Estimated {fuel: BFP c/l} and exchange rate for `target_day`, from official
    report `base`. Falls back to "dollar part unchanged, exchange rate updated" (and
    finally to "no change") when market data or fitted weights are missing."""
    fx = base.exchange_rate
    ratio = fx_ratio(market, base.report_date, target_day) if fx else None
    fx_est = fx * ratio if ratio else fx
    x = product_features(market, base.report_date, target_day)
    bfp = {}
    for fuel in fuels:
        b = base.bfp.get(fuel)
        if b is None:
            continue
        if not fx:
            bfp[fuel] = round(b, 3)
            continue
        usd_move = float(np.dot(weights[fuel], x)) if (x is not None and fuel in weights) else 0.0
        bfp[fuel] = round(b / fx * math.exp(usd_move) * fx_est, 3)
    return bfp, (round(fx_est, 4) if fx_est else None)
