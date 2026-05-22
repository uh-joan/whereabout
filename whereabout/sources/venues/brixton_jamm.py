from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id

_URL = "https://www.brixtonjamm.org/allevents"
_POSTCODE = "SW9 8JP"
_VENUE = "Brixton Jamm"
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}


class BrixtonJammSource(BaseSource):
    source_id = "venue_brixton_jamm"

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            r = httpx.get(_URL, headers=_HEADERS, timeout=10, follow_redirects=True)
            r.raise_for_status()
        except Exception:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        events = []
        for item in soup.select("div.summary-item"):
            try:
                title_a = item.select_one("a.summary-title-link")
                date_t = item.select_one("time.summary-metadata-item--date")
                if not title_a or not date_t:
                    continue
                title = title_a.get_text(strip=True)
                href = title_a.get("href", "")
                source_url = f"https://www.brixtonjamm.org{href}" if href.startswith("/") else href
                date_str = date_t.get_text(strip=True)
                naive = datetime.strptime(date_str, "%d %B %Y")
                local = naive.replace(hour=20, tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)
                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue
                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt_utc, title),
                    source_url=source_url,
                    title=title,
                    date_start_utc=dt_utc,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=[],
                    ticket_url=source_url,
                    raw_payload={},
                ))
            except Exception:
                continue
        return events
