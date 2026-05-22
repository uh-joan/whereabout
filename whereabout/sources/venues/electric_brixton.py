from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource

_URL = "https://www.electricbrixton.uk.com/events"
_POSTCODE = "SW2 1RJ"
_VENUE = "Electric Brixton"
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {
    "User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout",
    # site uses brotli compression which httpx cannot decode without the brotli library
    "Accept-Encoding": "identity",
}
_ORD_RE = re.compile(r"(\d+)(?:st|nd|rd|th)")


def _parse_date(date_str: str) -> datetime:
    clean = _ORD_RE.sub(r"\1", date_str).strip()
    return datetime.strptime(clean, "%d %B %Y")


class ElectricBrixtonSource(BaseSource):
    source_id = "venue_electric_brixton"

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            r = httpx.get(_URL, headers=_HEADERS, timeout=10, follow_redirects=True)
            r.raise_for_status()
        except Exception:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        events = []
        for post in soup.select("div.fl-post-grid-post"):
            try:
                title_el = post.select_one("h3.event-title")
                date_el = post.select_one("h4.event-date")
                meta = post.select_one("meta[itemprop='mainEntityOfPage']")
                ticket_el = post.select_one("li.ticket-btn a")
                if not title_el or not date_el:
                    continue
                title = title_el.get_text(strip=True)
                source_url = meta.get("itemid", _URL) if meta else _URL
                ticket_url = ticket_el.get("href") if ticket_el else None
                naive = _parse_date(date_el.get_text(strip=True))
                local = naive.replace(hour=20, tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)
                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue
                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=f"{_POSTCODE}_{dt_utc.date()}_{title[:40]}",
                    source_url=source_url,
                    title=title,
                    date_start_utc=dt_utc,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=["electronic"],
                    ticket_url=ticket_url,
                    raw_payload={},
                ))
            except Exception:
                continue
        return events
