"""
Government fuel levy changes that have been announced, kept by hand. The model
only forecasts the Basic Fuel Price part of the price change; a levy change
comes on top of it, so the site adds it to the forecast for the price change it
falls on and says so.

Each entry is a period of temporary relief: the levy is lower by that many cents
a litre from `start` to `end` (inclusive). Paraffin carries no fuel levy.

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

- DMPR, 3 Nov 2026 (reported by BusinessTech that day): slate levy up 48.18c/l,
  from 87.66c to 135.84c, from 4 Nov 2026 (slate -R15.876bn at end Sept).
"""
import datetime as dt

# Which levy rate each fuel pays. Paraffin isn't listed: it carries no fuel levy.
LEVY_FUELS = {"petrol95": "petrol", "petrol93": "petrol", "diesel005": "diesel", "diesel0005": "diesel"}

# The relief periods: cents a litre off the levy for petrol and diesel, dates
# inclusive, with when and where it was announced.
RELIEF = [
    {"start": dt.date(2026, 11, 4), "end": dt.date(2026, 12, 1), "petrol": 150, "diesel": 300,
     "announced": dt.date(2026, 10, 21), "source": "MTBPS"},
    {"start": dt.date(2026, 12, 2), "end": dt.date(2027, 1, 5), "petrol": 100, "diesel": 150,
     "announced": dt.date(2026, 10, 21), "source": "MTBPS"},
]


# Slate levy changes, in cents a litre on petrol and diesel, with the date the new
# level takes effect and when and where it was announced.
SLATE = [
    {"effective": dt.date(2026, 11, 4), "from": 87.66, "to": 135.84,
     "announced": dt.date(2026, 11, 3), "source": "DMPR"},
]


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
        "announced": announcer["announced"],
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
