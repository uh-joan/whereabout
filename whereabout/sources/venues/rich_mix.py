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

_CFG = load_venue_config("venue_rich_mix")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# Handles: "SUN 24 MAY", "Fri 29 May", "From Wed 25 Feb – ...", "Mon 1 Jun – ..."
_DATE_RE = re.compile(
    r"(?:From\s+)?(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})\s+([A-Za-z]{3})"
    r"|(\d{1,2})\s+([A-Za-z]{3})",
    re.I,
)


def _parse_rich_mix_date(text: str) -> tuple[int, int] | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    if m.group(1):
        day_str, month_str = m.group(1), m.group(2)
    else:
        day_str, month_str = m.group(3), m.group(4)
    try:
        dt = datetime.strptime(f"{day_str} {month_str}", "%d %b")
        return dt.day, dt.month
    except ValueError:
        return None


class RichMixSource(BaseSource):
    source_id = "venue_rich_mix"
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

        for card in soup.select(".tease-events"):
            try:
                article = card.find("article") or card
                h3 = article.find("h3")
                if not h3:
                    continue
                title = h3.get_text(strip=True)

                date_el = article.find(class_="date")
                if not date_el:
                    continue
                date_text = date_el.get_text(strip=True)

                parsed = _parse_rich_mix_date(date_text)
                if not parsed:
                    continue
                day, month = parsed

                dt_year = year
                if month < query.date_range_start_utc.month - 1:
                    dt_year = year + 1

                local = datetime(dt_year, month, day, _DEFAULT_HOUR, _DEFAULT_MIN, tzinfo=_LONDON_TZ)
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
