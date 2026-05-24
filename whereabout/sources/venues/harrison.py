from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_harrison")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_LONDON_TZ = ZoneInfo("Europe/London")

_SKIP_RE = re.compile(
    r"\bcomedy\b|\bstandup\b|\bstand.up\b|\bquiz\b|\bbingo\b|\bkaraoke\b|\bstandup\b|\bimprov\b",
    re.IGNORECASE,
)


def _parse_dt(date_text: str, time_text: str) -> datetime:
    # "Wednesday 27 May 2026" + "7:30 pm"
    combined = f"{date_text.strip()} {time_text.strip().upper()}"
    return datetime.strptime(combined, "%A %d %B %Y %I:%M %p")


class HarrisonSource(BaseSource):
    source_id = "venue_harrison"
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

        for art in soup.select(".mec-event-article"):
            try:
                title_el = art.select_one("h4.mec-event-title")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title or _SKIP_RE.search(title):
                    continue

                date_el = art.select_one("span.mec-start-date-label")
                time_el = art.select_one("span.mec-start-time")
                if not date_el or not time_el:
                    continue

                naive = _parse_dt(date_el.get_text(strip=True), time_el.get_text(strip=True))
                local = naive.replace(tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                event_id = venue_event_id(_POSTCODE, dt_utc, title)
                if event_id in seen:
                    continue
                seen.add(event_id)

                link_el = art.select_one("a.mec-booking-button, a.mec-color-hover")
                href = link_el["href"] if link_el and link_el.get("href") else _URL
                source_url = href if href.startswith("http") else _URL

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
