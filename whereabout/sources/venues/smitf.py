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

_CFG = load_venue_config("venue_smitf")
_AJAX_URL = "https://www.stmartin-in-the-fields.org/wp-admin/admin-ajax.php"
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {
    "User-Agent": "Mozilla/5.0 Chrome/124.0.0.0",
    "Content-Type": "application/x-www-form-urlencoded",
}

# Matches: "Friday 10 July, 7pm"  /  "Sunday 24 May, 3.15pm"  /  "Friday 13 November, 7:30pm"
# Also handles optional explicit year: "Friday 19 February 2027, 7:30pm"
_DATE_TIME_RE = re.compile(
    r"""
    (?:\w+\s+)?                           # optional day-of-week + space
    (\d{1,2})\s+(\w+)                     # day  month
    (?:\s+(\d{4}))?                       # optional explicit year
    ,\s*
    (\d{1,2})(?:[.:](\d{2}))?(am|pm)     # hour [.min] am/pm
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Matches bare dates (no time) in pipe-separated lists or plain:
# "6 June" / "Monday 4 May" / "Friday 11 December"
_BARE_DATE_RE = re.compile(
    r"""
    (?:\w+\s+)?          # optional day-of-week + space
    (\d{1,2})\s+(\w+)    # day  month
    (?:\s+(\d{4}))?      # optional explicit year
    """,
    re.VERBOSE,
)

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _to_24h(hour: int, minute: int, ampm: str) -> tuple[int, int]:
    ampm = ampm.lower()
    if ampm == "am":
        if hour == 12:
            hour = 0
    else:  # pm
        if hour != 12:
            hour += 12
    return hour, minute


def _infer_year(month: int, base_year: int, base_month: int) -> int:
    """Return the most likely year for an event with the given month."""
    if month < base_month - 1:
        return base_year + 1
    return base_year


def _parse_entries(date_text: str, base_year: int, base_month: int) -> list[tuple[int, int, int, int, int]]:
    """
    Return a list of (year, month, day, hour, minute) tuples parsed from a
    date string.  Handles:
      - Single date+time:  "Friday 10 July, 7pm"
      - Pipe-separated bare dates:  "6 June | 27 June | 11 July"
      - Explicit year:  "Friday 19 February 2027, 7:30pm"
    """
    results: list[tuple[int, int, int, int, int]] = []

    # Try single date+time first
    m = _DATE_TIME_RE.search(date_text)
    if m:
        day = int(m.group(1))
        month = _MONTH_MAP.get(m.group(2).lower())
        if not month:
            return results
        explicit_year = int(m.group(3)) if m.group(3) else None
        hour = int(m.group(4))
        minute = int(m.group(5)) if m.group(5) else 0
        hour, minute = _to_24h(hour, minute, m.group(6))
        year = explicit_year if explicit_year else _infer_year(month, base_year, base_month)
        results.append((year, month, day, hour, minute))
        return results

    # No time present — iterate over all bare dates (pipe-separated lists)
    for bm in _BARE_DATE_RE.finditer(date_text):
        day = int(bm.group(1))
        month = _MONTH_MAP.get(bm.group(2).lower())
        if not month:
            continue
        explicit_year = int(bm.group(3)) if bm.group(3) else None
        year = explicit_year if explicit_year else _infer_year(month, base_year, base_month)
        results.append((year, month, day, _DEFAULT_HOUR, _DEFAULT_MIN))

    return results


class SMITFSource(BaseSource):
    source_id = "venue_smitf"
    freshness_seconds = 6 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            r = httpx.post(
                _AJAX_URL,
                data={"action": "whatson_filter"},
                headers=_HEADERS,
                timeout=15,
                follow_redirects=True,
            )
            r.raise_for_status()
            payload = r.json()
            html = payload["data"]["html"]
        except Exception:
            return []

        soup = BeautifulSoup(html, "html.parser")
        events: list[RawEvent] = []
        base_year = query.date_range_start_utc.year
        base_month = query.date_range_start_utc.month

        for card in soup.select("li.WhatsonItem"):
            try:
                h3_a = card.select_one("h3 a")
                if not h3_a:
                    continue
                title = h3_a.get_text(strip=True)
                if not title:
                    title = h3_a.get("title", "").rstrip("link").strip()
                if not title:
                    continue

                source_url = h3_a.get("href") or _CFG["url"]

                date_span = card.select_one(".EV_ListDate .DateText")
                if not date_span:
                    continue
                date_text = date_span.get_text(strip=True)
                if not date_text:
                    continue

                entries = _parse_entries(date_text, base_year, base_month)
                for (year, month, day, hour, minute) in entries:
                    try:
                        local = datetime(year, month, day, hour, minute, tzinfo=_LONDON_TZ)
                    except ValueError:
                        continue
                    dt_utc = local.astimezone(timezone.utc)

                    if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                        continue

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
