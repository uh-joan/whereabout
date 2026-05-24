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

_CFG = load_venue_config("venue_cadogan_hall")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# Match the first date in strings like:
#   "Sunday 24 May 2026, 6.30pm"
#   "Thursday 28 May 2026, 7.30pm - Saturday 30 May 2026, 7.30pm"
# Group 1: full weekday+day+month+year  e.g. "Sunday 24 May 2026"
# Group 2: time string                  e.g. "6.30pm", "12pm", "11am"
_DATE_RE = re.compile(
    r"(\w+\s+\d{1,2}\s+\w+\s+\d{4})\s*,\s*([\d]+(?:\.[\d]+)?(?:am|pm))",
    re.I,
)


def _parse_cadogan_date(date_text: str) -> datetime | None:
    """Parse a Cadogan Hall date string into a London-local datetime, or None."""
    m = _DATE_RE.search(date_text)
    if not m:
        return None

    date_str = m.group(1)   # e.g. "Sunday 24 May 2026"
    time_str = m.group(2)   # e.g. "6.30pm", "12pm", "11am"

    try:
        date_part = datetime.strptime(date_str, "%A %d %B %Y")
    except ValueError:
        return None

    # Parse time: split on "." for optional minutes; strip am/pm suffix
    time_lower = time_str.lower()
    is_pm = time_lower.endswith("pm")
    time_digits = time_lower.rstrip("apm")  # e.g. "6.30" or "12" or "11"

    if "." in time_digits:
        h_str, m_str = time_digits.split(".", 1)
        hour, minute = int(h_str), int(m_str)
    else:
        hour, minute = int(time_digits), 0

    # Convert 12-hour to 24-hour
    if is_pm and hour != 12:
        hour += 12
    elif not is_pm and hour == 12:
        hour = 0

    return datetime(
        date_part.year, date_part.month, date_part.day,
        hour, minute,
        tzinfo=_LONDON_TZ,
    )


class CadoganHallSource(BaseSource):
    source_id = "venue_cadogan_hall"
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

        for card in soup.select(".c-event-item"):
            try:
                title_el = card.select_one(".c-event-item__heading")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                date_el = card.select_one(".c-event-item__date")
                if not date_el:
                    continue
                date_text = date_el.get_text(strip=True)

                local_dt = _parse_cadogan_date(date_text)
                if local_dt is None:
                    continue
                dt_utc = local_dt.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                # Prefer the "More Info" / first link; fall back to venue URL
                links = card.find_all("a", href=True)
                source_url = links[0]["href"] if links else _URL
                ticket_url = next(
                    (a["href"] for a in links if "book" in a.get("data-button", "").lower()),
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
