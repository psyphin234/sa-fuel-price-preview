"""
Fuel price headlines for the "In the news" panel: the latest stories about petrol,
diesel, the fuel and slate levies and oil prices, from South African publishers'
own RSS feeds. Only each story's headline, source, date and link are kept and
shown, never its text, and every link goes to the publisher.

Each feed is fetched at most once an hour (publish.py runs up to five times an
hour), into data/news_cache.json (gitignored); a feed that fails keeps its last
good copy. No API keys. app.py wraps the call so it can never stop a publish.
"""
import datetime as dt
import email.utils
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

FEEDS = [
    ("BusinessTech", "https://businesstech.co.za/news/energy/feed/"),
    ("The Citizen", "https://www.citizen.co.za/business/feed/"),
    ("Moneyweb", "https://www.moneyweb.co.za/feed/"),
    ("SABC News", "https://www.sabcnews.com/sabcnews/category/business/feed/"),
    ("Daily Maverick", "https://www.dailymaverick.co.za/dmrss/"),
]
CACHE_PATH = Path(__file__).parent.parent / "data" / "news_cache.json"
MAX_AGE = dt.timedelta(hours=1)    # how long a fetched feed is kept before trying again
MAX_DAYS = 14                      # older stories are dropped
MAX_ITEMS = 8
MAX_BYTES = 3_000_000              # a feed bigger than this is ignored
HEADERS = {"User-Agent": "PsyPhin fuel price tracker (RSS reader)"}
# A story counts if its headline or summary mentions one of these.
KEYWORDS = re.compile(
    r"\b(petrol|diesel|paraffin|fuel[- ](price|prices|levy|pump|pumps)|slate levy|brent|crude|"
    r"oil prices?|opec|hormuz|basic fuel price)\b", re.I)
TAGS = re.compile(r"<[^>]+>")


def _text(s: str) -> str:
    """Feed text as plain text: tags removed, entities decoded, spaces tidied."""
    return " ".join(html.unescape(TAGS.sub(" ", s or "")).split())


def parse(source: str, xml_bytes: bytes) -> list:
    """The fuel-related stories in one RSS feed: title, link, source, published (UTC)."""
    root = ET.fromstring(xml_bytes)
    stories = []
    for item in root.iter("item"):
        title = _text(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not title or not re.match(r"https?://", link):
            continue
        if not KEYWORDS.search(title + " " + _text(item.findtext("description"))):
            continue
        try:
            published = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "").astimezone(dt.timezone.utc)
        except (TypeError, ValueError):
            continue
        stories.append({"title": title, "link": link, "source": source, "published": published.isoformat()})
    return stories


def _fetch(url: str):
    r = requests.get(url, headers=HEADERS, timeout=10, stream=True)
    r.raise_for_status()
    body = r.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(body) > MAX_BYTES:
        raise ValueError("feed too large")
    return body


def get_news(now: dt.datetime = None) -> list:
    """The newest MAX_ITEMS fuel stories across all feeds, newest first, one per
    headline. Feeds are re-fetched once their cached copy is an hour old."""
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    changed = False
    for source, url in FEEDS:
        entry = cache.get(url)
        fresh = entry and now - dt.datetime.fromisoformat(entry["fetched_at"]) < MAX_AGE
        if fresh:
            continue
        try:
            cache[url] = {"fetched_at": now.isoformat(), "stories": parse(source, _fetch(url))}
        except Exception as e:  # keep the last good copy; try again next time
            print(f"news: {source} failed ({e}); keeping the last copy")
            # Don't retry on every run: wait the hour, as for a good fetch.
            cache[url] = {"fetched_at": now.isoformat(), "stories": entry["stories"] if entry else []}
        changed = True
    if changed:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, indent=1), encoding="utf-8")

    cutoff = now - dt.timedelta(days=MAX_DAYS)
    seen, stories = set(), []
    every = [s for e in cache.values() for s in e.get("stories", [])]
    for s in sorted(every, key=lambda s: s["published"], reverse=True):
        key = re.sub(r"\W+", " ", s["title"].lower()).strip()
        if key in seen or dt.datetime.fromisoformat(s["published"]) < cutoff:
            continue
        seen.add(key)
        stories.append(s)
    return stories[:MAX_ITEMS]
