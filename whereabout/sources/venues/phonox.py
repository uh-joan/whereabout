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

_CFG = load_venue_config("venue_phonox")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# "Fri 29 May" or "Sat 30 May"
_DATE_RE = re.compile(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})\s+(\w+)", re.I)
# "22:00" from "22:00 - 04:00"
_TIME_RE = re.compile(r"(\d{2}):(\d{2})\s*[-–]")


def _parse_phonox_date(text: str) -> tuple[int, int, int] | None:
    """Return (day, month_int, hour, min) from card text, or None."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:
        dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%a %d %b")
        return dt.day, dt.month
    except ValueError:
        return None


class PhonoxSource(BaseSource):
    source_id = "venue_phonox"
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
        year = query.date_range_start_utc.year

        for card in soup.select("div.whats-on"):
            try:
                h = card.find(["h2", "h3", "h4"])
                if not h:
                    continue
                title = h.get_text(strip=True)
                full_txt = card.get_text(" ", strip=True)

                parsed = _parse_phonox_date(full_txt)
                if not parsed:
                    continue
                day, month = parsed

                # Determine year (handle year roll-over)
                dt_year = year
                if month < query.date_range_start_utc.month - 1:
                    dt_year = year + 1

                # Extract start time
                tm = _TIME_RE.search(full_txt)
                hour = int(tm.group(1)) if tm else _DEFAULT_HOUR
                minute = int(tm.group(2)) if tm else _DEFAULT_MIN

                local = datetime(dt_year, month, day, hour, minute, tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                links = card.find_all("a", href=True)
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
