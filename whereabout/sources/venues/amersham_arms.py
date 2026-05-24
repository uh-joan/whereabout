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

_CFG = load_venue_config("venue_amersham_arms")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)", re.I)


def _parse_time(text: str) -> tuple[int, int]:
    m = _TIME_RE.search(text)
    if not m:
        return _DEFAULT_HOUR, _DEFAULT_MIN
    hour = int(m.group(1))
    minute = int(m.group(2))
    meridiem = m.group(3).lower()
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    return hour, minute


class AmershamArmsSource(BaseSource):
    source_id = "venue_amersham_arms"
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

        for article in soup.select("article.tribe-events-calendar-list__event"):
            try:
                h = article.find(["h2", "h3", "h4"])
                if not h:
                    continue
                title = h.get_text(strip=True)

                time_tag = article.find(
                    "time", class_="tribe-events-calendar-list__event-datetime"
                )
                if not time_tag or not time_tag.get("datetime"):
                    continue

                date_obj = datetime.strptime(time_tag["datetime"], "%Y-%m-%d")
                hour, minute = _parse_time(time_tag.get_text(" ", strip=True))

                local = datetime(
                    date_obj.year, date_obj.month, date_obj.day,
                    hour, minute, tzinfo=_LONDON_TZ
                )
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                links = article.find_all("a", href=True)
                source_url = links[0]["href"] if links else _URL
                ticket_url = next(
                    (a["href"] for a in links if "ticket" in a.get_text(strip=True).lower()),
                    source_url,
                )

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt_utc, title),
                    source_url=source_url,
                    title=title,
                    date_start_utc=dt_utc,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=_CFG["genres"],
                    ticket_url=ticket_url,
                    raw_payload={},
                ))
            except Exception:
                continue

        return events
