from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_ronnie_scotts")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}
# For range strings like "Mon 25 May - Mon 3 Aug 2026" we want day=25, month=May.
# Strategy: find the trailing year, then take the first "day month" pair in the string.
_YEAR_RE = re.compile(r"\b(\d{4})\b")
_DAY_MONTH_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\b")
_MONTH_NAMES = {
    m.lower() for m in [
        "jan", "feb", "mar", "apr", "may", "jun",
        "jul", "aug", "sep", "oct", "nov", "dec",
        "january", "february", "march", "april", "june", "july",
        "august", "september", "october", "november", "december",
    ]
}
# The JS inline script tells us totalPages; we also cap at _MAX_PAGES as a safety limit
_MAX_PAGES = 25


def _extract_first_date(text: str) -> tuple[str, str, str] | None:
    """Return (day, month, year) for the *start* date in a Ronnie's date string.

    Handles both single dates ("Fri 22  May 2026") and range strings
    ("Mon 25 May - Mon 3 Aug 2026") by finding the trailing year and then
    taking the first valid day+month pair that appears earlier in the string.
    """
    year_m = _YEAR_RE.search(text)
    if not year_m:
        return None
    year = year_m.group(1)
    for m in _DAY_MONTH_RE.finditer(text):
        day, month = m.group(1), m.group(2)
        if month.lower() in _MONTH_NAMES:
            return day, month, year
    return None


def _parse_listing_date(el) -> datetime:
    """Parse date from a div.listing element.

    The date sits in a plain <div> (no class) inside the listing card.
    """
    for div in el.find_all("div", recursive=False):
        if div.get("class"):
            continue
        text = div.get_text(separator=" ", strip=True)
        result = _extract_first_date(text)
        if result:
            day, month, year = result
            for fmt in ("%d %B %Y", "%d %b %Y"):
                try:
                    naive = datetime.strptime(f"{day} {month} {year}", fmt)
                    return naive.replace(
                        hour=_DEFAULT_HOUR, minute=_DEFAULT_MIN, tzinfo=_LONDON_TZ
                    ).astimezone(timezone.utc)
                except ValueError:
                    continue
    raise ValueError("date not found")


def _total_pages(html: str) -> int:
    """Extract totalPages from the inline JS snippet."""
    m = re.search(r"totalPages['\"]?\s*:\s*(\d+)", html)
    return int(m.group(1)) if m else 1


def _parse_page(html: str, query: Query) -> tuple[list[RawEvent], bool]:
    """Parse one page of listings. Returns (events, stop_early).

    stop_early=True when all remaining events are beyond the query window.
    """
    soup = BeautifulSoup(html, "html.parser")
    events: list[RawEvent] = []
    stop_early = False

    for el in soup.select("div.listing"):
        try:
            dt = _parse_listing_date(el)
        except Exception:
            continue

        if dt > query.date_range_end_utc:
            stop_early = True
            break

        if dt < query.date_range_start_utc:
            continue

        title_el = el.select_one("h2.listing__title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        btn = el.select_one("[data-show-event-url]")
        ticket_url = btn["data-show-event-url"] if btn else None

        events.append(RawEvent(
            source="venue_ronnie_scotts",
            source_event_id=venue_event_id(_POSTCODE, dt, title),
            source_url=ticket_url or _URL,
            title=title,
            date_start_utc=dt,
            venue_name=_VENUE,
            venue_postcode=_POSTCODE,
            genres_raw=_CFG["genres"],
            ticket_url=ticket_url,
            raw_payload={},
        ))

    return events, stop_early


class RonnieScottsSource(BaseSource):
    source_id = "venue_ronnie_scotts"
    freshness_seconds = 2 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        all_events: list[RawEvent] = []

        try:
            r = httpx.get(_URL, headers=_HEADERS, timeout=15, follow_redirects=True)
            r.raise_for_status()
        except Exception:
            return []

        total = min(_total_pages(r.text), _MAX_PAGES)
        page_events, stop = _parse_page(r.text, query)
        all_events.extend(page_events)

        for page_num in range(2, total + 1):
            if stop:
                break
            try:
                r = httpx.get(
                    f"{_URL}?page={page_num}",
                    headers=_HEADERS,
                    timeout=15,
                    follow_redirects=True,
                )
                r.raise_for_status()
            except Exception:
                break
            page_events, stop = _parse_page(r.text, query)
            all_events.extend(page_events)

        return all_events
