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

_CFG = load_venue_config("venue_dingwalls")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# "Saturday, 30th May, 2026"
_FMT1_RE = re.compile(r"(\w+),\s+(\d+)(?:st|nd|rd|th)\s+(\w+),?\s+(\d{4})", re.I)
# "Sunday, May 31st 2026"
_FMT2_RE = re.compile(r"(\w+),\s+(\w+)\s+(\d+)(?:st|nd|rd|th)\s+(\d{4})", re.I)


def _parse_dingwalls_date(text: str) -> tuple[int, int, int] | None:
    m = _FMT1_RE.search(text)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)}", "%d %B %Y")
            return dt.day, dt.month, dt.year
        except ValueError:
            pass

    m = _FMT2_RE.search(text)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(3)} {m.group(2)} {m.group(4)}", "%d %B %Y")
            return dt.day, dt.month, dt.year
        except ValueError:
            pass

    return None


class DingwallsSource(BaseSource):
    source_id = "venue_dingwalls"
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

        for card in soup.select(".gig"):
            try:
                h = card.find(["h1", "h2", "h3", "h4"])
                if not h:
                    continue
                title = h.get_text(strip=True)
                if not title:
                    continue

                date_p = card.find("p", class_="elementor-heading-title")
                date_text = date_p.get_text(strip=True) if date_p else card.get_text(" ", strip=True)

                parsed = _parse_dingwalls_date(date_text)
                if not parsed:
                    continue
                day, month, year = parsed

                local = datetime(year, month, day, _DEFAULT_HOUR, _DEFAULT_MIN, tzinfo=_LONDON_TZ)
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
