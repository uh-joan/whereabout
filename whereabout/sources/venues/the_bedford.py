from __future__ import annotations
import asyncio
import re
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_the_bedford")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")


def _parse_tribe_datetime(link_text: str) -> datetime:
    # "Wednesday May 27 from 7:00 pm"
    parts = link_text.split(" from ", 1)
    date_part = parts[0].strip()
    time_part = parts[1].strip().upper() if len(parts) > 1 else f"{_DEFAULT_HOUR}:{_DEFAULT_MIN:02d} PM"
    parsed = datetime.strptime(date_part, "%A %B %d")
    t = datetime.strptime(time_part, "%I:%M %p")
    today = date.today()
    candidate = parsed.replace(year=today.year, hour=t.hour, minute=t.minute)
    if candidate.date() < today:
        candidate = candidate.replace(year=today.year + 1)
    return candidate


class TheBedfordSource(BaseSource):
    source_id = "venue_the_bedford"
    live = False
    freshness_seconds = 6 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            from cloakbrowser import launch
        except ImportError:
            return []

        browser = None
        try:
            browser = launch(headless=True)
            page = browser.new_page()
            page.goto(_URL, timeout=30000)
            page.wait_for_timeout(3000)
            html = page.content()
        except Exception:
            return []
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

        soup = BeautifulSoup(html, "html.parser")
        events: list[RawEvent] = []
        seen: set[str] = set()

        for art in soup.find_all("article"):
            classes = " ".join(art.get("class", []))
            if "type-tribe_events" not in classes:
                continue
            try:
                heading = art.find(re.compile(r"^h[2-4]$"))
                if not heading:
                    continue
                title = heading.get_text(strip=True)
                if not title:
                    continue

                link_el = art.select_one("a.tribe-event-url")
                if not link_el:
                    continue
                link_text = link_el.get_text(strip=True)
                if " from " not in link_text:
                    continue
                href = link_el.get("href", _URL)
                source_url = href if href.startswith("http") else _URL

                naive = _parse_tribe_datetime(link_text)
                local = naive.replace(tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                event_id = venue_event_id(_POSTCODE, dt_utc, title)
                if event_id in seen:
                    continue
                seen.add(event_id)

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
