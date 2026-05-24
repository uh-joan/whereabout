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

_CFG = load_venue_config("venue_clapham_grand")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# Matches "Fri 29 May • 6pm" or "Thu 28 May •  6:30pm - 9:45pm"
# Groups: (day_name, day_num, month_name, time)
_DATE_RE = re.compile(
    r"(\w{3})\s+(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r".*?(\d{1,2}(?::\d{2})?(?:am|pm))",
    re.IGNORECASE,
)
_CURRENT_YEAR = None  # resolved at parse time from context


def _parse_card_date(text: str) -> datetime | None:
    """Parse date string from listing__date text, inferring year from proximity to today."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    day_num = int(m.group(2))
    month_name = m.group(3).capitalize()
    time_raw = m.group(4).lower()

    # Normalise time: "6pm" -> "06:00PM", "6:30pm" -> "06:30PM"
    if ":" in time_raw:
        t_part, ampm = re.match(r"(\d+:\d+)(am|pm)", time_raw).groups()
    else:
        t_part, ampm = re.match(r"(\d+)(am|pm)", time_raw).groups()
        t_part = f"{t_part}:00"

    # Try current year then next year — pick whichever gives a future-ish date
    for year_offset in (0, 1):
        from datetime import date as _date
        year = _date.today().year + year_offset
        try:
            naive = datetime.strptime(
                f"{day_num} {month_name} {year} {t_part}{ampm.upper()}",
                "%d %b %Y %I:%M%p",
            )
            return naive.replace(tzinfo=_LONDON_TZ).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


class ClaphamGrandSource(BaseSource):
    source_id = "venue_clapham_grand"
    freshness_seconds = 2 * 3600

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

        for card in soup.select("div.listing.plotCard"):
            title_el = card.select_one(".listing__title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            date_el = card.select_one(".listingDateTime span, .listingDateTime")
            if not date_el:
                continue
            dt = _parse_card_date(date_el.get_text(strip=True))
            if not dt:
                continue

            if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                continue

            link_el = card.select_one("a[href]")
            event_url = link_el["href"] if link_el else _URL

            events.append(RawEvent(
                source=self.source_id,
                source_event_id=venue_event_id(_POSTCODE, dt, title),
                source_url=event_url,
                title=title,
                date_start_utc=dt,
                venue_name=_VENUE,
                venue_postcode=_POSTCODE,
                genres_raw=_CFG["genres"],
                ticket_url=event_url,
                raw_payload={},
            ))

        return events
