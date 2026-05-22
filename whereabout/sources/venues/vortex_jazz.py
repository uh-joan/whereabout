from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id

_URL = "https://vortexjazz.co.uk/events/"
_POSTCODE = "N16 8JH"
_VENUE = "Vortex Jazz Club"
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}


class VortexJazzSource(BaseSource):
    source_id = "venue_vortex_jazz"

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
        current_date: datetime | None = None

        for el in soup.select("h2.event_list_date, article.post_entry"):
            if "event_list_date" in el.get("class", []):
                try:
                    current_date = datetime.strptime(
                        el.get_text(strip=True), "%a %d %B %Y"
                    ).replace(hour=19, minute=30, tzinfo=_LONDON_TZ).astimezone(timezone.utc)
                except ValueError:
                    current_date = None
                continue

            if not current_date:
                continue
            if not (query.date_range_start_utc <= current_date <= query.date_range_end_utc):
                continue

            title_el = el.select_one("a.post_title")
            if not title_el:
                continue
            title = title_el.get("title") or title_el.get_text(strip=True)
            event_url = title_el.get("href", _URL)

            events.append(RawEvent(
                source=self.source_id,
                source_event_id=venue_event_id(_POSTCODE, current_date, title),
                source_url=event_url,
                title=title,
                date_start_utc=current_date,
                venue_name=_VENUE,
                venue_postcode=_POSTCODE,
                genres_raw=["jazz"],
                ticket_url=event_url,
                raw_payload={},
            ))

        return events
