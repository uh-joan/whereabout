from __future__ import annotations
import re
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_waiting_room_n16")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_LONDON_TZ = ZoneInfo("Europe/London")

# "Tuesday, May 26, 19:30"
_DATE_RE = re.compile(r"(\w+,\s+\w+\s+\d+,\s+\d+:\d+)")


def _parse_waiting_room_date(text: str) -> datetime | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    raw = m.group(1)  # e.g. "Tuesday, May 26, 19:30"
    parsed = datetime.strptime(raw, "%A, %B %d, %H:%M")
    today = date.today()
    candidate = parsed.replace(year=today.year)
    if candidate.date() < today:
        candidate = candidate.replace(year=today.year + 1)
    return candidate


class WaitingRoomN16Source(BaseSource):
    source_id = "venue_waiting_room_n16"
    live = True
    freshness_seconds = 3 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        try:
            async with httpx.AsyncClient(
                timeout=15, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"}
            ) as client:
                r = await client.get(_URL)
            r.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        events: list[RawEvent] = []
        seen: set[str] = set()

        for item in soup.select("div.grid-item"):
            try:
                title_el = item.select_one("div.event_title")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title:
                    continue

                item_text = item.get_text(separator=" ", strip=True)
                naive = _parse_waiting_room_date(item_text)
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

                dice_link = item.find("a", href=lambda h: h and "dice.fm" in h)
                source_url = dice_link["href"] if dice_link else _URL

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=event_id,
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
