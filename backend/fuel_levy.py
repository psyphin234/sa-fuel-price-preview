"""
Government fuel levy changes that have been announced, kept by hand. The model
only forecasts the Basic Fuel Price part of the price change; a levy change
comes on top of it, so the site adds it to the forecast for the price change it
falls on and says so.

Each entry is a period of temporary relief: the levy is lower by that many cents
a litre from `start` to `end` (inclusive). Paraffin carries no fuel levy.

- Apr - Jun 2026, announced by the Minister of Finance and set out in the DMPR's
  monthly price statements (gov.za; BusinessTech for June, whose statement page
  couldn't be read): R3.00 petrol and diesel from 1 Apr to 5 May; R3.00 petrol and
  R3.93 diesel from 6 May to 2 Jun; cut by R1.50 and R1.96 from 3 Jun, leaving
  R1.50 and R1.97 to 30 Jun (derived); phased out from 1 Jul (full levies of 429c
  and 416c reinstated, 30 Jun statement).
- MTBPS, 21 Oct 2026 (Finance Minister Godongwana, reported by Moneyweb, SABC,
  The Citizen and others the same day): R3.00 diesel / R1.50 petrol from
  4 Nov to 1 Dec 2026, then R1.50 diesel / R1.00 petrol until 5 Jan 2027.
  The second tier's start (2 Dec, the December price change) is implied, not
  stated. Not yet gazetted when added; check the DMPR price announcement.

Add an entry when a new change is announced; old ones can stay.

The slate levy (SLATE below) is kept here too. It recovers the slate, the running
total of past under-recoveries, and the DMPR changes it in its monthly price
announcement, usually a day or two before the change. The model can't foresee it,
so enter it once announced; the forecast for that date then matches the official
figure. Petrol and diesel only, like the fuel levy.

Every slate levy change since the levy came back in May 2026 is listed, from the
DMPR's monthly statements (gov.za; Engineering News for 2 Sep 2026, whose statement
wasn't found). The October 2026 statement says 87.66c applied "from the 2nd of
September", but 83.28c did and 87.66c from 7 Oct (the November statement starts
from 87.66c): a copy error in the statement.

SLATE_BALANCES are the slate's month-end balances each statement quotes, the
figure that sets the levy two months later (slate_estimate.py uses them to
estimate the next change before it's announced). When the DMPR announces a month's
prices, enter both: the levy change in SLATE and the balance it quotes here.
"""
import datetime as dt

# Which levy rate each fuel pays. Paraffin isn't listed: it carries no fuel levy.
LEVY_FUELS = {"petrol95": "petrol", "petrol93": "petrol", "diesel005": "diesel", "diesel0005": "diesel"}

# The relief periods: cents a litre off the levy for petrol and diesel, dates
# inclusive, with when and where it was announced.
RELIEF = [
    {"start": dt.date(2026, 4, 1), "end": dt.date(2026, 5, 5), "petrol": 300, "diesel": 300,
     "announced": dt.date(2026, 3, 31), "source": "DMPR's price statement"},
    {"start": dt.date(2026, 5, 6), "end": dt.date(2026, 6, 2), "petrol": 300, "diesel": 393,
     "announced": dt.date(2026, 5, 5), "source": "DMPR's price statement"},
    # end_announced: when the end was announced, if not with the start
    {"start": dt.date(2026, 6, 3), "end": dt.date(2026, 6, 30), "petrol": 150, "diesel": 197,
     "announced": dt.date(2026, 6, 1), "end_announced": dt.date(2026, 6, 30), "source": "DMPR's price statement"},
    {"start": dt.date(2026, 11, 4), "end": dt.date(2026, 12, 1), "petrol": 150, "diesel": 300,
     "announced": dt.date(2026, 10, 21), "source": "MTBPS"},
    {"start": dt.date(2026, 12, 2), "end": dt.date(2027, 1, 5), "petrol": 100, "diesel": 150,
     "announced": dt.date(2026, 10, 21), "source": "MTBPS"},
]


# Slate levy changes, in cents a litre on petrol and diesel, with the date the new
# level takes effect and when and where it was announced.
SLATE = [
    {"effective": dt.date(2026, 5, 6), "from": 0.0, "to": 122.70, "announced": dt.date(2026, 5, 5), "source": "DMPR"},
    {"effective": dt.date(2026, 6, 3), "from": 122.70, "to": 157.74, "announced": dt.date(2026, 6, 1), "source": "DMPR"},
    {"effective": dt.date(2026, 7, 1), "from": 157.74, "to": 113.94, "announced": dt.date(2026, 6, 30), "source": "DMPR"},
    {"effective": dt.date(2026, 8, 5), "from": 113.94, "to": 61.38, "announced": dt.date(2026, 8, 3), "source": "DMPR"},
    {"effective": dt.date(2026, 9, 2), "from": 61.38, "to": 83.28, "announced": dt.date(2026, 8, 31), "source": "DMPR"},
    {"effective": dt.date(2026, 10, 7), "from": 83.28, "to": 87.66, "announced": dt.date(2026, 10, 5), "source": "DMPR"},
    {"effective": dt.date(2026, 11, 4), "from": 87.66, "to": 135.84, "announced": dt.date(2026, 11, 3), "source": "DMPR"},
]

# The cumulative petrol and diesel slate at month end, in R billion (negative: owed
# to the industry), as quoted in the statement for the price change `sets`. The
# levy was zero in every statement from Dec 2025 to Apr 2026 (the slate was in
# surplus); the Feb 2026 statement (end-Dec balance) wasn't found.
SLATE_BALANCES = [
    {"at": dt.date(2025, 10, 31), "balance": 4.36, "sets": dt.date(2025, 12, 3)},
    {"at": dt.date(2025, 11, 30), "balance": 3.3, "sets": dt.date(2026, 1, 7)},
    {"at": dt.date(2026, 1, 31), "balance": 5.9, "sets": dt.date(2026, 3, 4)},
    {"at": dt.date(2026, 2, 28), "balance": 4.93, "sets": dt.date(2026, 4, 1)},
    {"at": dt.date(2026, 3, 31), "balance": -14.173, "sets": dt.date(2026, 5, 6)},
    {"at": dt.date(2026, 4, 30), "balance": -18.28, "sets": dt.date(2026, 6, 3)},
    {"at": dt.date(2026, 5, 31), "balance": -13.32, "sets": dt.date(2026, 7, 1)},
    {"at": dt.date(2026, 6, 30), "balance": -7.418, "sets": dt.date(2026, 8, 5)},
    {"at": dt.date(2026, 7, 31), "balance": -9.519, "sets": dt.date(2026, 9, 2)},
    {"at": dt.date(2026, 8, 31), "balance": -10.45, "sets": dt.date(2026, 10, 7)},
    {"at": dt.date(2026, 9, 30), "balance": -15.876, "sets": dt.date(2026, 11, 4)},
]


def slate_level(day: dt.date) -> float:
    """The slate levy in force on `day`, c/l (zero before the first listed change)."""
    level = 0.0
    for s in sorted(SLATE, key=lambda s: s["effective"]):
        if s["effective"] <= day:
            level = s["to"]
    return level


def relief_on(day: dt.date):
    """The relief period in force on `day`, or None."""
    for r in RELIEF:
        if r["start"] <= day <= r["end"]:
            return r
    return None


def levy_change(previous_effective: dt.date, new_effective: dt.date, fuels: list):
    """The announced levy change between the price in force from `previous_effective`
    and the one from `new_effective`, in cents a litre per fuel (positive = the price
    rises). None if no announced change falls in between."""
    before, after = relief_on(previous_effective), relief_on(new_effective)
    if before is after:
        return None
    change = {}
    for fuel in fuels:
        kind = LEVY_FUELS.get(fuel)
        change[fuel] = ((before or {}).get(kind, 0) - (after or {}).get(kind, 0)) if kind else 0
    if not any(change.values()):
        return None
    announcer = after or before
    return {
        "effective": new_effective,
        "change": change,
        "announced": announcer["announced"] if after else before.get("end_announced", before["announced"]),
        "source": announcer["source"],
    }


def schedule(fuels: list) -> list:
    """Every relief period, with its cut in cents a litre per fuel, so the site can
    mark any price that has relief built in."""
    return [{"start": r["start"], "end": r["end"], "announced": r["announced"], "source": r["source"],
             "relief": {f: r.get(LEVY_FUELS.get(f), 0) for f in fuels}}
            for r in RELIEF]


def slate_change(previous_effective: dt.date, new_effective: dt.date, fuels: list):
    """The announced slate levy change between the price in force from
    `previous_effective` and the one from `new_effective`, in cents a litre per fuel
    (positive = the price rises), with the levy before and after. None if none."""
    steps = [s for s in SLATE if previous_effective < s["effective"] <= new_effective]
    if not steps:
        return None
    step = round(sum(s["to"] - s["from"] for s in steps), 2)
    return {
        "effective": new_effective,
        "change": {f: step if f in LEVY_FUELS else 0 for f in fuels},
        "from": steps[0]["from"],
        "to": steps[-1]["to"],
        "announced": steps[-1]["announced"],
        "source": steps[-1]["source"],
    }
