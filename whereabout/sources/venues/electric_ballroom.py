from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_electric_ballroom")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

_ORDINAL = re.compile(r"(\d+)(?:st|nd|rd|th)", re.IGNORECASE)
_SOLD_OUT = re.compile(r"\s*[-–]\s*SOLD\s*OUT[!.]?\s*$", re.IGNORECASE)


def _parse_datetime(date_text: str, time_text: str) -> datetime | None:
    # "Sunday 24th May" → "Sunday 24 May"
    date_clean = _ORDINAL.sub(r"\1", date_text).strip()
    now = datetime.now()
    for year in (now.year, now.year + 1):
        try:
            naive_date = datetime.strptime(f"{date_clean} {year}", "%A %d %B %Y")
            break
        except ValueError:
            continue
    else:
        return None

    hour, minute = _DEFAULT_HOUR, _DEFAULT_MIN
    if time_text:
        try:
            t = datetime.strptime(time_text.strip().upper(), "%I.%M%p")
            hour, minute = t.hour, t.minute
        except ValueError:
            pass

    # If parsed date is more than 30 days in the past, bump year
    naive = naive_date.replace(hour=hour, minute=minute)
    if naive < datetime.now() - timedelta(days=30):
        naive = naive.replace(year=naive.year + 1)
    return naive


class ElectricBallroomSource(BaseSource):
    source_id = "venue_electric_ballroom"
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

        for card in soup.select("div.grid-block.card"):
            try:
                h2 = card.select_one("h2.event-name a")
                if not h2:
                    continue
                title = _SOLD_OUT.sub("", h2.get_text(strip=True)).strip()

                date_el = card.select_one("span.event-date")
                time_el = card.select_one("span.event-time")
                if not date_el:
                    continue

                naive = _parse_datetime(
                    date_el.get_text(strip=True),
                    time_el.get_text(strip=True) if time_el else "",
                )
                if naive is None:
                    continue

                local = naive.replace(tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                link = card.select_one("a.grid-link[href]")
                source_url = link["href"] if link else _URL

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
