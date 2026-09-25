"""
Scrapes and parses CEF Group's official Daily Basic Fuel Price PDF reports.
Source: https://cefgroup.co.za/daily-basic-fuel-price/
URL pattern: https://cefgroup.co.za/wp-content/uploads/{upload YYYY}/{upload MM}/Daily-{DD}-{MM}-{YYYY}.pdf
"""
import re
import io
import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import requests
import pdfplumber

FUELS = ["petrol95", "petrol93", "diesel005", "diesel0005", "illpar"]
FUEL_LABELS = {
    "petrol95": "Petrol 95 ULP",
    "petrol93": "Petrol 93 ULP & LRP",
    "diesel005": "Diesel 0.05% S",
    "diesel0005": "Diesel 0.005% S",
    "illpar": "Illuminating Paraffin",
}

BASE_URL = "https://cefgroup.co.za/wp-content/uploads/{folder_year}/{folder_month:02d}/Daily-{day:02d}-{month:02d}-{year}.pdf"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BFP-preview-tool/1.0"}

NUM = r"\(?-?[\d,]+\.\d+\)?|-"


def _num(token: str) -> Optional[float]:
    token = token.strip()
    if token == "-" or token == "":
        return None
    neg = token.startswith("(") and token.endswith(")")
    token = token.strip("()").replace(",", "")
    val = float(token)
    return -val if neg else val


def _extract_row(text: str, label_pattern: str) -> Optional[list]:
    """Find a line starting with label_pattern followed by up to 5 numeric/dash tokens.
    Uses a named group for the numbers because label_pattern itself may contain
    capturing groups (e.g. embedded dates), which would otherwise shift group(1)."""
    pattern = rf"{label_pattern}\s+(?P<nums>(?:{NUM})(?:\s+(?:{NUM})){{0,4}})"
    m = re.search(pattern, text)
    if not m:
        return None
    tokens = re.findall(NUM, m.group("nums"))
    tokens = tokens[:5]
    return [_num(t) for t in tokens]


@dataclass
class DailyReport:
    report_date: dt.date
    period_start: dt.date          # start of the Platts averaging review period (drives NEXT price change)
    period_end: dt.date
    reference_valid_from: dt.date  # start of the date range the CURRENT reference/pump price has applied
    pump_price_effective: dt.date
    reference_price: dict = field(default_factory=dict)      # PRESS RELEASE CONTRIBUTION TO BFP (fixed for the pricing month)
    bfp: dict = field(default_factory=dict)                  # today's BASIC FUEL PRICE per fuel
    unit_over_under: dict = field(default_factory=dict)      # today's UNIT OVER/(UNDER) RECOVERY per fuel
    avg_bfp: dict = field(default_factory=dict)               # official AVERAGE BASIC FUEL PRICE for period-to-date
    avg_over_under: dict = field(default_factory=dict)        # official AVERAGE UNIT OVER/(UNDER) RECOVERY for period-to-date
    current_price: dict = field(default_factory=dict)         # current retail/wholesale/max price per fuel (whichever applies)
    exchange_rate: float = None
    source: str = "cef_official"


def fetch_pdf_bytes(date: dt.date) -> Optional[bytes]:
    """CEF uploads each report into the folder for the month it was *published*,
    so a month-end report (published on the 1st) sits in the next month's folder."""
    next_month = (date.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    for folder in (date, next_month):
        url = BASE_URL.format(folder_year=folder.year, folder_month=folder.month,
                              day=date.day, month=date.month, year=date.year)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException:
            continue
        if resp.status_code == 200 and resp.content.startswith(b"%PDF"):
            return resp.content
    return None


def parse_pdf(pdf_bytes: bytes) -> Optional[DailyReport]:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = pdf.pages[0].extract_text() or ""

    date_re = r"(\d{2})/(\d{2})/(\d{4})"

    m = re.search(rf"GAUTENG PUMP PRICE AS FROM {date_re}", text)
    if not m:
        return None
    pump_price_effective = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    m = re.search(rf"BASIC FUEL PRICE - {date_re}", text)
    if not m:
        return None
    report_date = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    m = re.search(rf"PRESS RELEASE CONTRIBUTION TO BFP {date_re} - {date_re}", text)
    if not m:
        return None
    reference_valid_from = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    m = re.search(rf"AVERAGE BASIC FUEL PRICE {date_re} - {date_re}", text)
    if not m:
        return None
    period_start = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    period_end = dt.date(int(m.group(6)), int(m.group(5)), int(m.group(4)))

    bfp_vals = _extract_row(text, rf"BASIC FUEL PRICE - {date_re}")
    ref_vals = _extract_row(text, rf"PRESS RELEASE CONTRIBUTION TO BFP {date_re} - {date_re}")
    unit_vals = _extract_row(text, rf"UNIT OVER/\(UNDER\) RECOVERY - {date_re}")
    avg_bfp_vals = _extract_row(text, rf"AVERAGE BASIC FUEL PRICE {date_re} - {date_re}")
    avg_unit_vals = _extract_row(text, rf"AVERAGE UNIT OVER/\(UNDER\) RECOVERY {date_re} - {date_re}")

    fx_m = re.search(r"R/\$EXCHANGE RATE - \(R/\$([\d.]+) - " + date_re + r"\)", text.replace(" ", ""))
    if not fx_m:
        fx_m = re.search(r"R/\$\s*([\d.]+)\s*-\s*" + date_re, text)
    exchange_rate = float(fx_m.group(1)) if fx_m else None

    def to_dict(vals):
        if not vals:
            return {}
        return {f: v for f, v in zip(FUELS, vals)}

    pump_vals = _extract_row(text, rf"GAUTENG PUMP PRICE AS FROM {date_re}")
    wholesale_vals = _extract_row(text, rf"WHOLESALE PRICE AS FROM {date_re}")
    maxretail_vals = _extract_row(text, rf"SINGLE NATIONAL MAXIMUM RETAIL PRICE AS FROM {date_re}")

    # each fuel column only ever has ONE of these three populated - merge into a single map
    current_price = {}
    for src in (pump_vals, wholesale_vals, maxretail_vals):
        d = to_dict(src)
        for k, v in d.items():
            if v is not None:
                current_price[k] = v

    return DailyReport(
        report_date=report_date,
        period_start=period_start,
        period_end=period_end,
        reference_valid_from=reference_valid_from,
        pump_price_effective=pump_price_effective,
        reference_price=to_dict(ref_vals),
        bfp=to_dict(bfp_vals),
        unit_over_under=to_dict(unit_vals),
        avg_bfp=to_dict(avg_bfp_vals),
        avg_over_under=to_dict(avg_unit_vals),
        current_price=current_price,
        exchange_rate=exchange_rate,
    )


def fetch_and_parse(date: dt.date) -> Optional[DailyReport]:
    raw = fetch_pdf_bytes(date)
    if raw is None:
        return None
    return parse_pdf(raw)


def find_latest_report(start_from: dt.date = None, max_lookback_days: int = 10) -> Optional[DailyReport]:
    """Walk backward from today (or start_from) until a published report is found."""
    d = start_from or dt.date.today()
    for _ in range(max_lookback_days):
        rep = fetch_and_parse(d)
        if rep is not None:
            return rep
        d -= dt.timedelta(days=1)
    return None


def backfill_period(period_start: dt.date, period_end: dt.date) -> list:
    """Fetch every published daily report between period_start and period_end (inclusive)."""
    reports = []
    d = period_start
    while d <= period_end:
        rep = fetch_and_parse(d)
        if rep is not None:
            reports.append(rep)
        d += dt.timedelta(days=1)
    return reports


if __name__ == "__main__":
    import json
    latest = find_latest_report()
    if latest:
        print("Latest report date:", latest.report_date)
        print("Period:", latest.period_start, "to", latest.period_end)
        print("Pump price effective:", latest.pump_price_effective)
        print("Exchange rate:", latest.exchange_rate)
        print("BFP:", latest.bfp)
        print("Reference price:", latest.reference_price)
        print("Unit over/under:", latest.unit_over_under)
        print("Avg BFP:", latest.avg_bfp)
        print("Avg over/under:", latest.avg_over_under)
    else:
        print("No report found")
