from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_jazz_cafe")
_URL = _CFG["url"]
_BASE = "https://thejazzcafe.com"
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

_GENRE_MAP: dict[str, list[str]] = {
    "jazz-improvised-music": ["jazz"],
    "soul-rnb": ["soul", "r&b"],
    "funk-disco": ["funk", "soul"],
    "african-diaspora": ["afrobeats", "world"],
    "electronic": ["electronic"],
    "hip-hop": ["hip-hop"],
    "reggae-dub": ["reggae"],
    "latin": ["latin"],
    "brazilian": ["latin", "world"],
    "blues-rock-folk": ["blues", "rock", "folk"],
    # legacy keys kept for safety
    "jazz": ["jazz"],
    "soul": ["soul"],
    "funk": ["funk"],
    "reggae": ["reggae"],
    "r-b": ["r&b"],
    "blues": ["blues"],
}


def _parse_genres(data_genre: str) -> list[str]:
    genres: set[str] = set()
    for g in data_genre.split("|"):
        genres.update(_GENRE_MAP.get(g.lower().strip(), []))
    return list(genres) or ["jazz", "soul", "funk"]


def _parse_date(el, query_start: datetime) -> datetime:
    date_el = el.select_one(".event-date")
    if not date_el:
        raise ValueError("no .event-date")
    parts = date_el.get_text(separator=" ").split()
    year = datetime.now(_LONDON_TZ).year
    naive = datetime.strptime(f"{parts[1]} {parts[2]} {year}", "%d %b %Y")
    local = naive.replace(hour=20, tzinfo=_LONDON_TZ)
    if local.astimezone(timezone.utc) < query_start:
        local = local.replace(year=year + 1)
    return local.astimezone(timezone.utc)


class JazzCafeSource(BaseSource):
    source_id = "venue_jazz_cafe"
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

        for el in soup.select("li.event"):
            if el.get("data-outsidelondon", "no") == "yes":
                continue
            try:
                dt = _parse_date(el, query.date_range_start_utc)
                if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                    continue

                title_el = el.select_one("h2.event-title")
                if not title_el:
                    continue
                title = title_el.get_text(separator=" ", strip=True)

                link_el = el.select_one("a[href]")
                ticket_url = link_el["href"] if link_el else None
                if ticket_url and ticket_url.startswith("/"):
                    ticket_url = _BASE + ticket_url

                genres = _parse_genres(el.get("data-genre", ""))

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt, title),
                    source_url=ticket_url or _URL,
                    title=title,
                    date_start_utc=dt,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=genres,
                    ticket_url=ticket_url,
                    raw_payload={},
                ))
            except Exception:
                continue
        return events
