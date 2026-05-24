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

_CFG = load_venue_config("venue_africa_centre")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}
_BASE_URL = "https://www.africacentre.org.uk"

# Human-readable time text: "5th August, 2026 at 1:00pm"
# Used instead of the datetime attribute because the attribute omits AM/PM
_TIME_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)\s+(\w+),\s+(\d{4})\s+at\s+(\d{1,2}:\d{2}(?:am|pm))",
    re.IGNORECASE,
)
_MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


def _parse_time_text(text: str) -> datetime | None:
    """Parse 'Xth Month, YYYY at H:MMam/pm' -> UTC datetime."""
    m = _TIME_RE.search(text)
    if not m:
        return None
    day, month_name, year, time_str = m.group(1), m.group(2), m.group(3), m.group(4)
    month = _MONTH_MAP.get(month_name.capitalize())
    if not month:
        return None
    try:
        naive = datetime.strptime(
            f"{day} {month} {year} {time_str.upper()}", "%d %m %Y %I:%M%p"
        )
        return naive.replace(tzinfo=_LONDON_TZ).astimezone(timezone.utc)
    except ValueError:
        return None


class AfricaCentreSource(BaseSource):
    source_id = "venue_africa_centre"
    freshness_seconds = 3 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            r = httpx.get(_URL, headers=_HEADERS, timeout=10, follow_redirects=True)
            r.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        events: list[RawEvent] = []

        for card in soup.select("section.listedEvent"):
            title_el = card.find(["h2", "h3", "h4", "h5"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)

            # Parse start time from human-readable text in p.associatedStartDate
            start_p = card.select_one("p.associatedStartDate")
            dt: datetime | None = None
            if start_p:
                dt = _parse_time_text(start_p.get_text(strip=True))

            # Fallback: use ISO datetime attribute (date only, no reliable time)
            if dt is None:
                start_time = card.select_one("p.associatedStartDate time[datetime]")
                if start_time:
                    raw_dt = start_time.get("datetime", "")
                    try:
                        # ISO date only e.g. "2026-06-05"
                        naive = datetime.strptime(raw_dt[:10], "%Y-%m-%d")
                        dt = naive.replace(hour=19, minute=0, tzinfo=_LONDON_TZ).astimezone(timezone.utc)
                    except ValueError:
                        continue

            if dt is None:
                continue

            if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                continue

            # End time
            dt_end: datetime | None = None
            end_p = card.select_one("p.associatedEndDate")
            if end_p:
                dt_end = _parse_time_text(end_p.get_text(strip=True))

            link_el = card.select_one("a[href]")
            href = link_el["href"] if link_el else ""
            event_url = f"{_BASE_URL}{href}" if href.startswith("/") else (href or _URL)

            events.append(RawEvent(
                source=self.source_id,
                source_event_id=venue_event_id(_POSTCODE, dt, title),
                source_url=event_url,
                title=title,
                date_start_utc=dt,
                date_end_utc=dt_end,
                venue_name=_VENUE,
                venue_postcode=_POSTCODE,
                genres_raw=_CFG["genres"],
                ticket_url=event_url,
                raw_payload={},
            ))

        return events
