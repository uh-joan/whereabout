from __future__ import annotations
import asyncio
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_hackney_empire")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}


class HackneyEmpireSource(BaseSource):
    source_id = "venue_hackney_empire"
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

        for card in soup.select("div.c-media.c-media--event"):
            try:
                h3 = card.find("h3", class_="c-media__title")
                if not h3:
                    continue
                title = h3.get_text(strip=True)

                time_el = card.find("time", datetime=True)
                if not time_el:
                    continue
                dt_utc = datetime.fromisoformat(time_el["datetime"]).astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                link = card.find("a", href=True)
                source_url = link["href"] if link else _URL

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt_utc, title),
                    source_url=source_url,
                    title=title,
                    date_start_utc=dt_utc,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=_CFG["genres"],
                    ticket_url=source_url,
                    raw_payload={},
                ))
            except Exception:
                continue

        return events
