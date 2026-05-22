from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id

_URL = "https://cafeoto.co.uk/events/"
_POSTCODE = "E8 3DL"
_VENUE = "Cafe OTO"
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}
# "Friday 22 May 2026, 7.30pm"
_DATE_RE = re.compile(r"(\w+ \d+ \w+ \d{4}),\s*([\d\.]+(?:am|pm))", re.IGNORECASE)
_EVENT_HREF_RE = re.compile(r"^/events/(?!archive)[^/]+/$")


def _parse_date(date_str: str, time_str: str) -> datetime:
    time_norm = time_str.replace(".", ":")
    naive = datetime.strptime(f"{date_str} {time_norm}", "%A %d %B %Y %I:%M%p")
    return naive.replace(tzinfo=_LONDON_TZ).astimezone(timezone.utc)


class CafeOtoSource(BaseSource):
    source_id = "venue_cafe_oto"

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

        for card in soup.select("div.each-activity"):
            link = card.find("a", href=_EVENT_HREF_RE)
            if not link:
                continue
            try:
                raw_text = card.get_text(separator=" ", strip=True)
                m = _DATE_RE.search(raw_text)
                if not m:
                    continue
                dt = _parse_date(m.group(1), m.group(2))
            except Exception:
                continue

            if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                continue

            headers = card.select("div.each-header")
            title = headers[-1].get_text(strip=True) if len(headers) >= 2 else ""
            if not title:
                continue
            event_url = f"https://cafeoto.co.uk{link['href']}"

            events.append(RawEvent(
                source=self.source_id,
                source_event_id=venue_event_id(_POSTCODE, dt, title),
                source_url=event_url,
                title=title,
                date_start_utc=dt,
                venue_name=_VENUE,
                venue_postcode=_POSTCODE,
                genres_raw=["experimental", "jazz"],
                ticket_url=event_url,
                raw_payload={},
            ))

        return events
