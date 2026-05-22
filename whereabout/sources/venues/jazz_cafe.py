from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_jazz_cafe")
_URL = _CFG["url"]
_BASE = "https://thejazzcafe.com"
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_LONDON_TZ = ZoneInfo("Europe/London")

_GENRE_MAP: dict[str, list[str]] = {
    "jazz": ["jazz"],
    "soul": ["soul"],
    "funk": ["funk"],
    "african-diaspora": ["afrobeats", "soul"],
    "electronic": ["electronic"],
    "hip-hop": ["hip-hop"],
    "reggae": ["reggae"],
    "latin": ["soul"],
    "r-b": ["r&b"],
    "blues": ["blues"],
}


def _parse_genres(data_genre: str) -> list[str]:
    genres: set[str] = set()
    for g in data_genre.split("|"):
        genres.update(_GENRE_MAP.get(g.lower(), []))
    return list(genres) or ["jazz", "soul", "funk"]


def _parse_date(el, query_start: datetime) -> datetime:
    date_el = el.select_one(".event-date")
    if not date_el:
        raise ValueError("no .event-date")
    parts = date_el.get_text(separator=" ").split()
    # parts: ['Fri', '22', 'May'] — day-of-week, day-number, month-abbrev
    year = datetime.now(_LONDON_TZ).year
    naive = datetime.strptime(f"{parts[1]} {parts[2]} {year}", "%d %b %Y")
    local = naive.replace(hour=20, tzinfo=_LONDON_TZ)
    if local.astimezone(timezone.utc) < query_start:
        local = local.replace(year=year + 1)
    return local.astimezone(timezone.utc)


class JazzCafeSource(BaseSource):
    source_id = "venue_jazz_cafe"
    live = False

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            from cloakbrowser import launch
            from bs4 import BeautifulSoup
        except ImportError:
            return []
        browser = None
        try:
            browser = launch(headless=True)
            page = browser.new_page()
            page.goto(_URL, timeout=30000)
            page.wait_for_selector("li.event", timeout=15000)
            html = page.content()
        except Exception:
            return []
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
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
