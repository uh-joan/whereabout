from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource

_BASE_URL = "https://www.songkick.com/metro-areas/24426-uk-london/calendar"
_HEADERS = {
    "User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout",
    "Accept-Language": "en-GB,en;q=0.9",
}
_MAX_PAGES = 10
# Split "Artist A, Artist B, and Artist C" into individual names
_ARTIST_SPLIT_RE = re.compile(r",\s*(?:and\s+)?|\s+and\s+")


def _artists_from_strong(text: str) -> list[str]:
    parts = _ARTIST_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _postcode_for_city(city: str) -> str | None:
    from whereabout import neighbourhoods as nb
    resolved = nb.resolve_name(city)
    if not resolved:
        return None
    for n in nb._NEIGHBOURHOODS:
        if n["name"] == resolved:
            prefixes = n.get("postcode_prefixes", [])
            return prefixes[0] if prefixes else None
    return None


class SongkickSource(BaseSource):
    source_id = "songkick"
    live = True

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        events: list[RawEvent] = []
        for page in range(1, _MAX_PAGES + 1):
            url = _BASE_URL if page == 1 else f"{_BASE_URL}?page={page}"
            try:
                resp = httpx.get(url, headers=_HEADERS, timeout=15, follow_redirects=True)
                resp.raise_for_status()
            except Exception:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.select("li.event-listings-element")
            if not items:
                break

            past_range = False
            for li in items:
                time_el = li.select_one("time[datetime]")
                if not time_el or not time_el.get("datetime"):
                    continue
                try:
                    dt = datetime.fromisoformat(time_el["datetime"]).astimezone(timezone.utc)
                except ValueError:
                    continue

                if dt > query.date_range_end_utc:
                    past_range = True
                    break
                if dt < query.date_range_start_utc:
                    continue

                strong_el = li.select_one("p.artists a.event-link strong")
                if not strong_el:
                    continue
                strong_text = strong_el.get_text(strip=True)
                artists = _artists_from_strong(strong_text)

                support_el = li.select_one("p.artists a.event-link span.support")
                if support_el:
                    for name in _artists_from_strong(support_el.get_text(strip=True)):
                        if name not in artists:
                            artists.append(name)

                title = strong_text

                venue_el = li.select_one("p.location a.venue-link")
                venue_name = venue_el.get_text(strip=True) if venue_el else ""

                city_el = li.select_one("p.location span.city-name")
                city = city_el.get_text(strip=True).split(",")[0].strip() if city_el else ""
                postcode = _postcode_for_city(city)

                link_el = li.select_one("a.event-link[href]")
                event_path = link_el["href"] if link_el else ""
                event_url = f"https://www.songkick.com{event_path}" if event_path else _BASE_URL
                event_id = event_path.rstrip("/").split("/")[-1]

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=event_id,
                    source_url=event_url,
                    title=title,
                    date_start_utc=dt,
                    venue_name=venue_name,
                    venue_postcode=postcode,
                    artists=artists,
                    ticket_url=event_url,
                    raw_payload={},
                ))

            if past_range:
                break

        return events
