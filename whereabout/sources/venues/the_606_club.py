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

_CFG = load_venue_config("venue_606_club")
_BASE = "https://www.606club.co.uk"
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}
_ORD_RE = re.compile(r"(\d+)(?:st|nd|rd|th)?([A-Z][a-z])")


def _parse_banner_date(text: str) -> datetime:
    # After <sup> decompose: "Mon 18May - 8:00pm"; with ordinal: "Mon 18th May - 8:00pm"
    # Insert space between digit and capitalised month abbreviation
    clean = _ORD_RE.sub(r"\1 \2", text)
    parts = clean.split(" - ")
    date_part = parts[0].strip()
    time_part = parts[1].strip() if len(parts) > 1 else "8:00pm"
    year = datetime.now(_LONDON_TZ).year
    naive = datetime.strptime(f"{date_part} {year} {time_part}", "%a %d %b %Y %I:%M%p")
    return naive


class The606ClubSource(BaseSource):
    source_id = "venue_606_club"
    freshness_seconds = 2 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        events: list[RawEvent] = []
        # Walk weekly pages until we've covered the full date range
        current = query.date_range_start_utc.date()
        end = query.date_range_end_utc.date()
        seen_urls: set[str] = set()
        while current <= end:
            url = f"{_URL}?d={current}#events"
            try:
                r = httpx.get(url, headers=_HEADERS, timeout=10, follow_redirects=True)
                r.raise_for_status()
            except Exception:
                break
            soup = BeautifulSoup(r.text, "html.parser")
            found_any = False
            for listing in soup.select("div.event-listing"):
                try:
                    banner = listing.select_one("a.banner")
                    h4 = listing.select_one("p.h4")
                    if not banner or not h4:
                        continue
                    href = banner.get("href", "")
                    event_url = f"{_BASE}{href}" if href.startswith("/") else href
                    if event_url in seen_urls:
                        continue
                    seen_urls.add(event_url)
                    found_any = True
                    # strip <sup> tags from banner text before parsing
                    for sup in banner.find_all("sup"):
                        sup.decompose()
                    banner_text = banner.get_text(strip=True)
                    naive = _parse_banner_date(banner_text)
                    # Infer year: if parsed date is in the past relative to start, bump year
                    local = naive.replace(tzinfo=_LONDON_TZ)
                    if local.date() < query.date_range_start_utc.date():
                        local = local.replace(year=local.year + 1)
                    dt_utc = local.astimezone(timezone.utc)
                    if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                        continue
                    title = h4.get_text(strip=True)
                    events.append(RawEvent(
                        source=self.source_id,
                        source_event_id=venue_event_id(_POSTCODE, dt_utc, title),
                        source_url=event_url,
                        title=title,
                        date_start_utc=dt_utc,
                        venue_name=_VENUE,
                        venue_postcode=_POSTCODE,
                        genres_raw=_CFG["genres"],
                        ticket_url=event_url,
                        raw_payload={},
                    ))
                except Exception:
                    continue
            # Advance by 7 days (each page shows a week)
            current += timedelta(days=7)
        return events
