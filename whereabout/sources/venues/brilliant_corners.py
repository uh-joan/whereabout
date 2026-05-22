from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource

_URL = "https://brilliantcornerslondon.co.uk/dates/"
_POSTCODE = "E8 4AE"
_VENUE = "Brilliant Corners"
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}


class BrilliantCornersSource(BaseSource):
    source_id = "venue_brilliant_corners"

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            r = httpx.get(_URL, headers=_HEADERS, timeout=10, follow_redirects=True)
            r.raise_for_status()
        except Exception:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        lefts = soup.select("div.dates-left-inner")
        middles = soup.select("div.dates-middle-inner")
        events = []
        for left, middle in zip(lefts, middles):
            try:
                date_str = left.get_text(strip=True)
                title = middle.get_text(strip=True)
                naive = datetime.strptime(date_str, "%a %d %b %y")
                local = naive.replace(hour=20, tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)
                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue
                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=f"{_POSTCODE}_{dt_utc.date()}_{title[:40]}",
                    source_url=_URL,
                    title=title,
                    date_start_utc=dt_utc,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=["jazz"],
                    ticket_url=None,
                    raw_payload={},
                ))
            except Exception:
                continue
        return events
