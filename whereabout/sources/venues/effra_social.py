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

_CFG = load_venue_config("venue_effra_social")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_SKIP_KEYWORDS = re.compile(
    r"burger|quiz|darts|karaoke|private hire|brunch|breakfast|comedy night|world cup|fifa|football|sport",
    re.IGNORECASE,
)


class EffraSocialSource(BaseSource):
    source_id = "venue_effra_social"
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

        for art in soup.select("article.tribe_events"):
            try:
                h3 = art.select_one("h3")
                if not h3:
                    continue
                title = h3.get_text(strip=True)
                if _SKIP_KEYWORDS.search(title):
                    continue

                date_str = time_str = None
                for t in art.select("time[datetime]"):
                    dt_val = t.get("datetime", "")
                    if _DATE_RE.match(dt_val):
                        date_str = dt_val
                    elif _TIME_RE.match(dt_val):
                        time_str = dt_val

                if not date_str:
                    continue

                if time_str:
                    hour, minute = map(int, time_str.split(":"))
                else:
                    hour, minute = _DEFAULT_HOUR, _DEFAULT_MIN

                naive = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    hour=hour, minute=minute
                )
                local = naive.replace(tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                a = art.select_one("a[href]")
                source_url = a["href"] if a else _URL

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
