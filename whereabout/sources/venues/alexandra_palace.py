from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_alexandra_palace")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}


def _parse_date(text: str) -> tuple[int, int, int] | None:
    """Parse '22 May 2026' → (day, month, year), or None."""
    try:
        dt = datetime.strptime(text.strip(), "%d %B %Y")
        return dt.day, dt.month, dt.year
    except ValueError:
        return None


class AlexandraPalaceSource(BaseSource):
    source_id = "venue_alexandra_palace"
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

        for card in soup.select("div.event_card_wrapper"):
            try:
                # Date: <p class="dates uc"><strong>22 May 2026</strong></p>
                date_tag = card.select_one("p.dates strong")
                if not date_tag:
                    continue
                parsed = _parse_date(date_tag.get_text(strip=True))
                if not parsed:
                    continue
                day, month, year = parsed

                # Title: <a class="event_target"><h3>...</h3></a>
                title_tag = card.select_one("a.event_target h3")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)

                # URL: <a class="event_target" href="...">
                link_tag = card.select_one("a.event_target")
                source_url = link_tag["href"] if link_tag and link_tag.get("href") else _URL

                local = datetime(year, month, day, _DEFAULT_HOUR, _DEFAULT_MIN, tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

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
