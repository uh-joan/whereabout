from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id

_URL = "https://hootanannybrixton.co.uk/"
_POSTCODE = "SW2 1DF"
_VENUE = "Hootananny Brixton"
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}
_TITLE_RE = re.compile(r"More Info on (.+?) Hootananny", re.IGNORECASE)


class HootanannySource(BaseSource):
    source_id = "venue_hootananny"
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
        events = []
        for band in soup.select("div.single_band"):
            try:
                month_str = band.get("data-month", "")
                showtype = band.get("data-showtype", "")
                a = band.find("a")
                if not a:
                    continue
                title_attr = a.get("title", "")
                m = _TITLE_RE.search(title_attr)
                title = m.group(1).strip() if m else a.get_text(strip=True)
                href = a.get("href", "")
                source_url = f"{_URL.rstrip('/')}/{href.lstrip('/')}" if href else _URL

                day_div = band.select_one("div.e-date")
                month_div = band.select_one("div.e-mnth")
                if not day_div or not month_div or not month_str:
                    continue
                day = day_div.get_text(strip=True)
                month_name = month_div.get_text(strip=True)
                year = month_str.split()[-1] if month_str.split() else ""
                naive = datetime.strptime(f"{day} {month_name} {year}", "%d %b %Y")
                local = naive.replace(hour=20, tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)
                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue
                genres = [g.strip().lower() for g in showtype.split(",") if g.strip()]
                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt_utc, title),
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
