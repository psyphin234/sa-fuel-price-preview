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
