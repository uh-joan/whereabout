from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_underworld_camden")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# The homepage lists events in div.feed-list#all (all), #gigs, #club-nights.
# Each event is <article class="list clearfix"> containing:
#   <header class="list-header">
#     <h3 class="list-header-title"><a href="...">TITLE</a></h3>
#     <p class="list-header-date"><time datetime="YYYY-MM-DD">...</time></p>
#   </header>


class UnderworldCamdenSource(BaseSource):
    source_id = "venue_underworld_camden"
    freshness_seconds = 2 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            r = httpx.get(_URL, headers=_HEADERS, timeout=15, follow_redirects=True)
            r.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        events: list[RawEvent] = []
        seen: set[str] = set()

        # Use #all to avoid duplicates from #gigs / #club-nights sub-lists
        feed = soup.find("div", class_="feed-list", id="all")
        if not feed:
            return []

        for card in feed.find_all("article", class_="list"):
            try:
                time_tag = card.find("time", attrs={"datetime": True})
                if not time_tag:
                    continue
                date_str = time_tag["datetime"]  # "YYYY-MM-DD"
                date_parts = date_str.split("-")
                if len(date_parts) != 3:
                    continue
                year, month, day = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])

                local = datetime(year, month, day, _DEFAULT_HOUR, _DEFAULT_MIN, tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                title_el = card.select_one("h3.list-header-title a, h3.list-header-title")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title:
                    continue

                # Skip cancelled events
                if "CANCELLED" in title.upper():
                    continue

                link_el = card.select_one("a[href*='/event/']")
                source_url = link_el["href"] if link_el else _URL

                event_id = venue_event_id(_POSTCODE, dt_utc, title)
                if event_id in seen:
                    continue
                seen.add(event_id)

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=event_id,
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
