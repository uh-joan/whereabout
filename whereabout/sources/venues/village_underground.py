from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id

_URL = "https://villageunderground.co.uk/events/"
_POSTCODE = "EC2A 3PQ"
_VENUE = "Village Underground"
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {
    "User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout",
    "Accept-Encoding": "identity",
}


class VillageUndergroundSource(BaseSource):
    source_id = "venue_village_underground"

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
        for item in soup.select("li.list--events__item"):
            try:
                start_time_el = item.select_one("time[itemprop='startDate']")
                title_el = item.select_one("h3.list--events__item__title")
                link_el = item.select_one("a.event-image") or item.select_one("div.list--events__item__link a")
                if not start_time_el or not title_el:
                    continue
                dt_str = start_time_el.get("datetime", "")
                if not dt_str:
                    continue
                # datetime attr is ISO: "2026-05-22T23:00:00+00:00"
                dt_utc = datetime.fromisoformat(dt_str).astimezone(timezone.utc)
                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue
                title = title_el.get_text(strip=True)
                source_url = link_el.get("href", _URL) if link_el else _URL
                if source_url.startswith("/"):
                    source_url = f"https://villageunderground.co.uk{source_url}"
                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt_utc, title),
                    source_url=source_url,
                    title=title,
                    date_start_utc=dt_utc,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=["electronic", "indie"],
                    ticket_url=source_url,
                    raw_payload={},
                ))
            except Exception:
                continue
        return events
