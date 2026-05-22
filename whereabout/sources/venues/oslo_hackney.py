from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id

_URL = "https://www.oslohackney.com/events/"
_POSTCODE = "E8 2LX"
_VENUE = "Oslo Hackney"
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {
    "User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout",
    "Accept-Encoding": "identity",
}

# Date format: "Fri.22.May.26" → parse as "%a.%d.%b.%y"
_DATE_FORMAT = "%a.%d.%b.%y"


def _parse_oslo_date(text: str) -> datetime:
    """Parse Oslo date string like 'Fri.22.May.26'."""
    clean = text.strip()
    return datetime.strptime(clean, _DATE_FORMAT)


class OsloHackneySource(BaseSource):
    source_id = "venue_oslo_hackney"
    freshness_seconds = 2 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            r = httpx.get(_URL, headers=_HEADERS, timeout=10, follow_redirects=True, verify=False)
            r.raise_for_status()
        except Exception:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        events = []
        for card in soup.select("div.card.card--full"):
            try:
                date_el = card.select_one("h6.card__strip-heading")
                title_el = card.select_one("a.card__heading--gig")
                ticket_el = card.select_one("a.js-gig-guide-tickets")
                if not date_el or not title_el:
                    continue
                date_str = date_el.get_text(strip=True)
                naive = _parse_oslo_date(date_str)
                local = naive.replace(hour=20, minute=0, tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)
                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue
                title = title_el.get_text(strip=True)
                source_url = title_el.get("href", _URL)
                ticket_url = ticket_el.get("href") if ticket_el else source_url
                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt_utc, title),
                    source_url=source_url,
                    title=title,
                    date_start_utc=dt_utc,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=["electronic", "indie"],
                    ticket_url=ticket_url,
                    raw_payload={},
                ))
            except Exception:
                continue
        return events
