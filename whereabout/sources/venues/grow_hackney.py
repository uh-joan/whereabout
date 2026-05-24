from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_grow_hackney")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# Grow titles often end with "(DISCO, SOUL, HOUSE)" — extract and use as genres
_GENRE_TAG = re.compile(r"\s*\(([A-Z][A-Z,/ ]+)\)\s*$")


def _parse_genres(title: str) -> tuple[str, list[str]]:
    m = _GENRE_TAG.search(title)
    if m:
        genres = [g.strip().lower() for g in m.group(1).split(",") if g.strip()]
        clean_title = title[: m.start()].strip()
        return clean_title, genres
    return title, _CFG["genres"]


class GrowHackneySource(BaseSource):
    source_id = "venue_grow_hackney"
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
        seen: set[str] = set()
        events: list[RawEvent] = []

        for article in soup.select("article"):
            try:
                h1 = article.select_one("h1")
                if not h1:
                    continue
                raw_title = h1.get_text(strip=True)

                time_el = article.select_one("time[datetime]")
                if not time_el:
                    continue
                date_str = time_el["datetime"]  # "YYYY-MM-DD"
                naive = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    hour=_DEFAULT_HOUR, minute=_DEFAULT_MIN
                )
                local = naive.replace(tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                title, genres = _parse_genres(raw_title)
                event_id = venue_event_id(_POSTCODE, dt_utc, title)
                if event_id in seen:
                    continue
                seen.add(event_id)

                a = article.select_one("a[href]")
                href = a["href"] if a else ""
                source_url = (
                    f"https://growhackney.co.uk{href}"
                    if href.startswith("/")
                    else href or _URL
                )

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=event_id,
                    source_url=source_url,
                    title=title,
                    date_start_utc=dt_utc,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=genres,
                    ticket_url=source_url,
                    raw_payload={},
                ))
            except Exception:
                continue

        return events
