from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_xoyo")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# Date block shows "23 May" (no year) — infer year from context
_DATE_RE = re.compile(r"^(\d{1,2})\s+(\w+)$")


def _infer_year(day: int, month_str: str) -> int:
    """Pick the nearest upcoming year for a given day/month."""
    today = date.today()
    try:
        candidate = date(today.year, datetime.strptime(month_str, "%B").month, day)
    except ValueError:
        return today.year
    # If the date has already passed this year, bump to next year
    if candidate < today:
        return today.year + 1
    return today.year


def _parse_date(date_text: str) -> datetime | None:
    """Parse "23 May" -> UTC datetime using default club time."""
    m = _DATE_RE.match(date_text.strip())
    if not m:
        return None
    try:
        day = int(m.group(1))
        month_str = m.group(2)
        month = datetime.strptime(month_str, "%b").month  # abbreviated e.g. "May"
        full_month = datetime(2000, month, 1).strftime("%B")
        year = _infer_year(day, full_month)
        local = datetime(year, month, day, _DEFAULT_HOUR, _DEFAULT_MIN, tzinfo=_LONDON_TZ)
        return local.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


class XoyoSource(BaseSource):
    source_id = "venue_xoyo"
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
        seen: set[str] = set()

        for block in soup.select("div.event-details"):
            try:
                date_hs = block.select("div.date-block h4")
                title_el = block.select_one("div.event-title-holder h2")
                link_el = block.select_one("div.event-title-holder a[href]")
                if not (date_hs and title_el):
                    continue

                # date-block has two <h4>: day-of-week and "23 May"
                date_text = date_hs[1].get_text(strip=True) if len(date_hs) > 1 else date_hs[0].get_text(strip=True)
                dt = _parse_date(date_text)
                if not dt:
                    continue

                title = title_el.get_text(strip=True)
                if not title:
                    continue

                # Deduplicate — same event appears twice in the Webflow DOM
                key = f"{dt.date()}|{title}"
                if key in seen:
                    continue
                seen.add(key)

                if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                    continue

                href = link_el["href"] if link_el else ""
                event_url = f"https://www.xoyo.co.uk{href}" if href.startswith("/") else href or _URL

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
            except Exception:
                continue

        return events
