from __future__ import annotations
import asyncio
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_toulouse_lautrec")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")


def _parse_tl_date(day: str, num: str, month: str) -> datetime:
    # e.g. "Fri", "22", "May" → parse via strptime, infer year
    parsed = datetime.strptime(f"{day} {num} {month}", "%a %d %b")
    today = date.today()
    candidate = parsed.replace(year=today.year, hour=_DEFAULT_HOUR, minute=_DEFAULT_MIN)
    if candidate.date() < today:
        candidate = candidate.replace(year=today.year + 1)
    return candidate


class ToulouseLautrecSource(BaseSource):
    source_id = "venue_toulouse_lautrec"
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

        for card in soup.select(".gb-component-event-card"):
            try:
                day_el = card.select_one(".gb-component-event-card__day")
                date_el = card.select_one(".gb-component-event-card__date")
                month_el = card.select_one(".gb-component-event-card__month")
                title_el = card.select_one(".gb-component-event-card__heading")
                if not (day_el and date_el and month_el and title_el):
                    continue

                title = title_el.get_text(strip=True)
                if not title:
                    continue

                naive = _parse_tl_date(
                    day_el.get_text(strip=True),
                    date_el.get_text(strip=True),
                    month_el.get_text(strip=True),
                )
                local = naive.replace(tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                event_id = venue_event_id(_POSTCODE, dt_utc, title)
                if event_id in seen:
                    continue
                seen.add(event_id)

                link_el = card.select_one("a[href*=event_calendar]")
                source_url = link_el["href"] if link_el else _URL

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
