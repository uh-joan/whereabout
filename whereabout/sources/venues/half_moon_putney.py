from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_half_moon_putney")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_LONDON_TZ = ZoneInfo("Europe/London")

# "May 2nd 2026, 11:00 AM" → strip ordinals → "%B %d %Y, %I:%M %p"
_ORDINAL_RE = re.compile(r"(\d+)(?:st|nd|rd|th)\b")
_SKIP_RE = re.compile(r"\bquiz\b|\bkaraoke\b|\bpub\s+quiz\b|\bchess\b|\bfooty\b|\bbingo\b", re.IGNORECASE)


def _parse_date(text: str) -> datetime:
    clean = _ORDINAL_RE.sub(r"\1", text).strip()
    return datetime.strptime(clean, "%B %d %Y, %I:%M %p")


class HalfMoonPutneySource(BaseSource):
    source_id = "venue_half_moon_putney"
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

        for art in soup.select("article[class*='EventCard']"):
            try:
                title_el = art.select_one("h1")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title or _SKIP_RE.search(title):
                    continue

                date_el = art.select_one("p[class*=date]")
                if not date_el:
                    continue
                naive = _parse_date(date_el.get_text(strip=True))
                local = naive.replace(tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                event_id = venue_event_id(_POSTCODE, dt_utc, title)
                if event_id in seen:
                    continue
                seen.add(event_id)

                link_el = art.select_one("a[href]")
                href = link_el["href"] if link_el else ""
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
