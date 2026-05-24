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

_CFG = load_venue_config("venue_barbican")
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}
_BASE = "https://www.barbican.org.uk"
_PAGES = [
    ("https://www.barbican.org.uk/whats-on/classical-music", ["classical", "orchestral", "opera", "chamber"]),
    ("https://www.barbican.org.uk/whats-on/contemporary-music", ["contemporary", "electronic", "experimental", "world", "jazz"]),
]

# Date formats emitted by p.listing-date:
#   "Mon 1 Jun 2026, 19:30"       single event with time
#   "Mon 1 Jun 2026"              single event, no time
#   "Mon 1–Mon 8 Jun 2026"        date range, same month
#   "Sun 24–Thu 28 May 2026"      date range, start day only
_TIME_RE = re.compile(r",\s*(\d{1,2}):(\d{2})")
_END_DATE_RE = re.compile(r"(\d{1,2})\s+(\w{3})\s+(\d{4})\s*$")
_START_DAY_RE = re.compile(r"(\d{1,2})")


def _parse_date(date_text: str) -> datetime | None:
    time_m = _TIME_RE.search(date_text)
    hour = int(time_m.group(1)) if time_m else _DEFAULT_HOUR
    minute = int(time_m.group(2)) if time_m else _DEFAULT_MIN

    clean = _TIME_RE.sub("", date_text).strip()
    parts = clean.split("–")  # en-dash
    start_part = parts[0].strip()

    # Try parsing start_part directly: "Mon 1 Jun 2026" or "Mon 1"
    try:
        naive = datetime.strptime(start_part, "%a %d %b %Y")
        return naive.replace(hour=hour, minute=minute)
    except ValueError:
        pass

    # Multi-span: start_part has day only ("Sun 24"), get month+year from end
    end_part = parts[-1].strip() if len(parts) > 1 else start_part
    end_m = _END_DATE_RE.search(end_part)
    if not end_m:
        return None
    month_str, year_str = end_m.group(2), end_m.group(3)
    day_m = _START_DAY_RE.search(start_part)
    if not day_m:
        return None
    try:
        naive = datetime.strptime(f"{day_m.group(1)} {month_str} {year_str}", "%d %b %Y")
        return naive.replace(hour=hour, minute=minute)
    except ValueError:
        return None


class BarbicanSource(BaseSource):
    source_id = "venue_barbican"
    freshness_seconds = 3 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        seen: set[str] = set()
        events: list[RawEvent] = []

        for url, page_genres in _PAGES:
            try:
                r = httpx.get(url, headers=_HEADERS, timeout=10, follow_redirects=True)
                r.raise_for_status()
            except Exception:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            for art in soup.select("article.listing--event"):
                try:
                    h2 = art.select_one("h2")
                    if not h2:
                        continue
                    title = h2.get_text(strip=True)

                    date_el = art.select_one("p.listing-date")
                    if not date_el:
                        continue
                    naive = _parse_date(date_el.get_text(strip=True))
                    if naive is None:
                        continue
                    local = naive.replace(tzinfo=_LONDON_TZ)
                    dt_utc = local.astimezone(timezone.utc)

                    if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                        continue

                    event_id = venue_event_id(_POSTCODE, dt_utc, title)
                    if event_id in seen:
                        continue
                    seen.add(event_id)

                    link = art.select_one("a.search-listing__link[href]")
                    source_url = f"{_BASE}{link['href']}" if link else url

                    events.append(RawEvent(
                        source=self.source_id,
                        source_event_id=event_id,
                        source_url=source_url,
                        title=title,
                        date_start_utc=dt_utc,
                        venue_name=_VENUE,
                        venue_postcode=_POSTCODE,
                        genres_raw=page_genres,
                        ticket_url=source_url,
                        raw_payload={},
                    ))
                except Exception:
                    continue

        return events
