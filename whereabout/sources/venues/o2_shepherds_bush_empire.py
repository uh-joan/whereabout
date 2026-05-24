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

_CFG = load_venue_config("venue_o2_shepherds_bush_empire")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_BASE_URL = "https://www.academymusicgroup.com"
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# Date format produced by the AMG MUI cards: "26 MAY 2026", "3 JUN 2026"
_DATE_FMT = "%d %b %Y"


def _parse_card_date(text: str) -> datetime | None:
    """Parse '26 MAY 2026' style date string into a London-timezone datetime."""
    try:
        dt = datetime.strptime(text.strip().upper(), _DATE_FMT)
        local = dt.replace(hour=_DEFAULT_HOUR, minute=_DEFAULT_MIN, tzinfo=_LONDON_TZ)
        return local.astimezone(timezone.utc)
    except ValueError:
        return None


class O2ShepherdsBushEmpireSource(BaseSource):
    source_id = "venue_o2_shepherds_bush_empire"
    freshness_seconds = 2 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            r = httpx.get(_URL, headers=_HEADERS, timeout=12, follow_redirects=True)
            r.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        events: list[RawEvent] = []
        seen_hrefs: set[str] = set()

        # The venue homepage renders MUI card <li> elements in static HTML.
        # Each card contains a single <a> whose text concatenates title + date.
        # e.g. "Marco Travaglio|26 MAY 2026" or "New|Deaf Havana|6 NOV 2026"
        for card in soup.find_all("li", class_=lambda c: c and "MuiCard-root" in c):
            link = card.find(
                "a",
                href=lambda h: h and "/o2shepherdsbushempire/events/" in h,
            )
            if not link:
                continue

            href = link["href"]
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            source_url = _BASE_URL + href if href.startswith("/") else href

            # Split on pipe separator, drop "New" badge and "Tickets" label
            parts = [
                p for p in link.get_text(separator="|", strip=True).split("|")
                if p and p.lower() not in ("new", "tickets")
            ]

            # Last part that looks like a date (digits + abbreviated month + year)
            date_str = None
            name_parts: list[str] = []
            for p in parts:
                if re.search(
                    r"^\d{1,2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{4}$",
                    p.strip(),
                    re.IGNORECASE,
                ):
                    date_str = p.strip()
                else:
                    name_parts.append(p)

            if not date_str or not name_parts:
                continue

            title = " ".join(name_parts)
            dt_utc = _parse_card_date(date_str)
            if dt_utc is None:
                continue

            if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                continue

            events.append(
                RawEvent(
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
                )
            )

        return events
