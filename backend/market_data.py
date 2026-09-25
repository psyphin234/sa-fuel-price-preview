"""
Free, keyless live quotes (Yahoo Finance) for the dashboard's current USD/ZAR
rate and benchmark display: Brent (BZ=F), RBOB gasoline (RB=F), NY Harbor
ULSD/heating oil (HO=F) and USD/ZAR (ZAR=X). The estimates themselves are made
in nowcast.py, from hourly prices.
"""
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BFP-preview-tool/1.0"}
YF_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

SYMBOLS = {
    "brent": "BZ=F",
    "rbob_gasoline": "RB=F",
    "ulsd_heating_oil": "HO=F",
    "usdzar": "ZAR=X",
}


def _fetch_symbol(symbol: str, range_: str = "10d", interval: str = "1d") -> dict:
    url = YF_CHART_URL.format(symbol=symbol)
    resp = requests.get(url, headers=HEADERS, params={"range": range_, "interval": interval}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    result = data["chart"]["result"][0]
    meta = result["meta"]
    closes = result["indicators"]["quote"][0]["close"]
    timestamps = result["timestamp"]
    valid = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
    if len(valid) < 2:
        raise ValueError(f"Not enough data points for {symbol}")
    latest_close = valid[-1][1]
    prev_close = valid[-2][1]

    # Prefer Yahoo's own meta change-% (computed against the official previous close);
    # the raw daily-bar close array can include a still-forming "today" bar or a
    # contract-rollover discontinuity that produces a misleading close-to-close delta.
    market_price = meta.get("regularMarketPrice", latest_close)
    market_change_pct = meta.get("regularMarketChangePercent")
    if market_change_pct is not None:
        pct_change = market_change_pct / 100.0
        prev_price = market_price / (1 + pct_change) if (1 + pct_change) != 0 else prev_close
    else:
        pct_change = (latest_close - prev_close) / prev_close
        prev_price = prev_close

    return {
        "symbol": symbol,
        "price": market_price,
        "prev_price": prev_price,
        "pct_change": pct_change,
        "regular_market_price": market_price,
        "regular_market_change_pct": market_change_pct,
    }


def fetch_all_benchmarks() -> dict:
    """Returns {name: {price, prev_price, pct_change, ...}} for all tracked symbols.
    Any symbol that fails to fetch is simply omitted (caller should handle missing keys)."""
    out = {}
    for name, symbol in SYMBOLS.items():
        try:
            out[name] = _fetch_symbol(symbol)
        except Exception as e:
            out[name] = {"error": str(e)}
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_all_benchmarks(), indent=2))
