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

_CFG = load_venue_config("venue_lso_st_lukes")
_BASE_URL = "https://www.lso.co.uk"
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# "Sunday 24 May 2026 • 7pm" or "Wednesday 10 June 2026 • 1pm" or "Friday 12 June 2026 • 12.30pm"
_DATE_RE = re.compile(
    r"\w+\s+(\d{1,2})\s+(\w+)\s+(\d{4})\s*[•·]\s*([\d\.]+(?:am|pm))",
    re.IGNORECASE,
)


def _parse_date(date_text: str) -> datetime | None:
    m = _DATE_RE.search(date_text)
    if not m:
        return None
    try:
        day, month_str, year, time_str = m.group(1), m.group(2), m.group(3), m.group(4)
        time_norm = time_str.replace(".", ":")
        naive = datetime.strptime(f"{day} {month_str} {year} {time_norm}", "%d %B %Y %I:%M%p")
        return naive.replace(tzinfo=_LONDON_TZ).astimezone(timezone.utc)
    except ValueError:
        return None


def _fetch_page(url: str) -> list[tuple[str, str, str]]:
    """Fetch one listing page; return list of (title, date_text, event_url)."""
    try:
        r = httpx.get(url, headers=_HEADERS, timeout=10, follow_redirects=True)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for card in soup.select(".c-event-card"):
        # Title: visible text in <span class="u-hidden-visually"> inside the link,
        # or the .c-event-card__title element
        title_el = card.select_one(".c-col-title, .c-event-card__title")
        if not title_el:
            link_el = card.select_one("a.c-event-card__link")
            title_el = link_el.select_one("span") if link_el else None
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        date_el = card.select_one(".c-event-card__date")
        date_text = date_el.get_text(strip=True) if date_el else ""
        if not date_text:
            continue

        link_el = card.select_one("a.c-event-card__link[href]")
        href = link_el["href"] if link_el else ""
        event_url = href if href.startswith("http") else f"{_BASE_URL}{href}"

        results.append((title, date_text, event_url))

    # Return next-page URL if present
    next_link = soup.select_one("a.next.page-numbers[href]")
    next_url = next_link["href"] if next_link else None
    return results, next_url  # type: ignore[return-value]


class LsoStLukesSource(BaseSource):
    source_id = "venue_lso_st_lukes"
    freshness_seconds = 6 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        events: list[RawEvent] = []
        url: str | None = _URL
        pages_fetched = 0

        while url and pages_fetched < 12:
            raw, next_url = _fetch_page(url)
            pages_fetched += 1
            any_in_range = False

            for title, date_text, event_url in raw:
                dt = _parse_date(date_text)
                if not dt:
                    continue
                if dt > query.date_range_end_utc:
                    continue
                if dt < query.date_range_start_utc:
                    continue
                any_in_range = True

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt, title),
                    source_url=event_url,
                    title=title,
                    date_start_utc=dt,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=_CFG["genres"],
                    ticket_url=event_url,
                    raw_payload={},
                ))

            # Stop paginating if all events on this page are past the end of the query window
            all_past_end = all(
                (lambda dt: dt is not None and dt > query.date_range_end_utc)(_parse_date(date_text))
                for _, date_text, _ in raw
            ) if raw else False
            if all_past_end:
                break

            url = next_url

        return events
