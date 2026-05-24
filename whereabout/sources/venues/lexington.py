from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_lexington")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

_BASE_URL = "https://thelexington.co.uk"


class LexingtonSource(BaseSource):
    source_id = "venue_lexington"
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
        year = query.date_range_start_utc.year

        for card in soup.select("div.grid-item, div.grid-item-club"):
            try:
                title_el = card.select_one(".event-title")
                date_el = card.select_one(".event-date")
                if not title_el or not date_el:
                    continue

                title = title_el.get_text(strip=True)
                date_text = date_el.get_text(strip=True)  # e.g. "Sun May 24, 19:30"

                try:
                    parsed = datetime.strptime(date_text, "%a %b %d, %H:%M")
                except ValueError:
                    continue

                month = parsed.month
                day = parsed.day
                hour = parsed.hour
                minute = parsed.minute

                dt_year = year
                if month < query.date_range_start_utc.month - 1:
                    dt_year = year + 1

                local = datetime(dt_year, month, day, hour, minute, tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                ticket_el = card.select_one("a.ticket-box")
                readmore_el = card.select_one("a.link-box")

                ticket_url = ticket_el["href"] if ticket_el and ticket_el.get("href") else _URL

                if readmore_el and readmore_el.get("href"):
                    href = readmore_el["href"]
                    source_url = href if href.startswith("http") else _BASE_URL + "/" + href.lstrip("./")
                else:
                    source_url = _URL

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt_utc, title),
                    source_url=source_url,
                    title=title,
                    date_start_utc=dt_utc,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=_CFG["genres"],
                    ticket_url=ticket_url,
                    raw_payload={},
                ))
            except Exception:
                continue

        return events
