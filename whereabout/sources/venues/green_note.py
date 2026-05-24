from __future__ import annotations
import asyncio
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_green_note")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# Date strings on listing page: "Sun 24th May" (no year, no time)
_DATE_RE = re.compile(r"^\w+\s+(\d+)\w*\s+(\w+)$")
_MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _infer_year(month: int, prev_month: int, current_year: int) -> int:
    """Increment year when month rolls back (events are in ascending order)."""
    if prev_month and month < prev_month:
        return current_year + 1
    return current_year


class GreenNoteSource(BaseSource):
    source_id = "venue_green_note"
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

        # Infer year from today; listing is always ascending from current date
        current_year = query.date_range_start_utc.year
        prev_month = 0

        for card in soup.select("div.wp_theatre_event"):
            title_el = card.select_one("div.wp_theatre_event_title")
            dt_el = card.select_one("div.wp_theatre_event_datetime")
            link_el = card.select_one("a")

            if not title_el or not dt_el:
                continue

            title = title_el.get_text(strip=True)
            dt_text = dt_el.get_text(strip=True)

            m = _DATE_RE.match(dt_text)
            if not m:
                continue

            day = int(m.group(1))
            month_abbr = m.group(2)[:3].capitalize()
            month = _MONTH_MAP.get(month_abbr)
            if not month:
                continue

            current_year = _infer_year(month, prev_month, current_year)
            prev_month = month

            try:
                dt = datetime(
                    current_year, month, day,
                    _DEFAULT_HOUR, _DEFAULT_MIN,
                    tzinfo=_LONDON_TZ,
                ).astimezone(timezone.utc)
            except ValueError:
                continue

            if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                continue

            # Skip cancelled events
            status_el = card.select_one("span.wp_theatre_event_tickets_status_cancelled")
            if status_el:
                continue

            event_url = link_el["href"] if link_el else _URL
            price_el = card.select_one("div.wp_theatre_event_prices")
            price_text = price_el.get_text(strip=True) if price_el else None

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
                price_text=price_text,
                raw_payload={"date_text": dt_text},
            ))

        return events
