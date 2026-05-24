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

_CFG = load_venue_config("venue_windmill_brixton")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

_DATE_IN_HREF = re.compile(r"/events/(\d{4}-\d{2}-\d{2})-")
_TIME_IN_TEXT = re.compile(r"(\d{1,2}:\d{2}\s*(?:AM|PM))", re.IGNORECASE)
_TRAILING_JUNK = re.compile(
    r"\s+(£[\d.]+|FREE|SOLD\s*OUT|More\s*inf.*|tba\.?)$", re.IGNORECASE
)


class WindmillBrixtonSource(BaseSource):
    source_id = "venue_windmill_brixton"
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

        for a in soup.select('a.EventLink[href^="/events/"]'):
            try:
                href = a["href"]
                date_m = _DATE_IN_HREF.search(href)
                if not date_m:
                    continue
                date_str = date_m.group(1)  # "YYYY-MM-DD"

                text = a.get_text(" ", strip=True)
                time_m = _TIME_IN_TEXT.search(text)
                if time_m:
                    naive = datetime.strptime(
                        f"{date_str} {time_m.group(1).strip()}", "%Y-%m-%d %I:%M %p"
                    )
                else:
                    naive = datetime.strptime(date_str, "%Y-%m-%d").replace(
                        hour=_DEFAULT_HOUR, minute=_DEFAULT_MIN
                    )

                local = naive.replace(tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                # Strip leading "Sat, May 23 8:00 PM " and trailing price/status
                title = re.sub(r"^.*?\b(?:AM|PM)\b\s*", "", text, flags=re.IGNORECASE)
                title = _TRAILING_JUNK.sub("", title).strip()
                if not title:
                    continue

                source_url = f"https://www.windmillbrixton.co.uk{href}"
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
