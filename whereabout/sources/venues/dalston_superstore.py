from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_dalston_superstore")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}


def _parse_iso(dt_str: str) -> datetime | None:
    """Parse ISO-8601 date from <time datetime> attribute, e.g. '2026-05-29'."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            naive = datetime.strptime(dt_str, fmt)
            if fmt == "%Y-%m-%d":
                naive = naive.replace(hour=_DEFAULT_HOUR, minute=_DEFAULT_MIN)
            return naive.replace(tzinfo=_LONDON_TZ).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


class DalstonSuperstoreSource(BaseSource):
    source_id = "venue_dalston_superstore"
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

        # The Events Calendar (tribe_events) — each event is an <article class="tribe-events-calendar-list__event ...">
        for card in soup.select("article.tribe_events"):
            # Title
            title_el = card.select_one(
                ".tribe-event-url, "
                ".tribe-events-calendar-list__event-title-link, "
                "h2 a, h3 a"
            )
            if not title_el:
                title_el = card.find(["h2", "h3", "h4"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            # Date — prefer <time datetime="YYYY-MM-DD">
            time_el = card.find("time", attrs={"datetime": True})
            if not time_el:
                continue
            dt = _parse_iso(time_el["datetime"])
            if not dt:
                continue

            if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                continue

            # Event URL
            link_el = card.select_one("a[href*='/event/']") or card.find("a", href=True)
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
