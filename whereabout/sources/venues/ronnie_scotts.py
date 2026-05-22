from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_ronnie_scotts")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
# "Fri 22  May 2026" or "Fri 22  - Sat 23 May 2026" — capture first date only
_DATE_RE = re.compile(r"\w+\s+(\d+)\s+(?:-\s*\w+\s+\d+\s+)?(\w+)\s+(\d{4})")


def _parse_date(el) -> datetime:
    for div in el.find_all("div", recursive=False):
        if div.get("class"):
            continue
        text = div.get_text(separator=" ", strip=True)
        m = _DATE_RE.search(text)
        if m:
            day, month, year = m.groups()
            naive = datetime.strptime(f"{day} {month} {year}", "%d %B %Y")
            return naive.replace(hour=_DEFAULT_HOUR, minute=_DEFAULT_MIN, tzinfo=_LONDON_TZ).astimezone(timezone.utc)
    raise ValueError("date not found")


class RonnieScottsSource(BaseSource):
    source_id = "venue_ronnie_scotts"
    live = False

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            from cloakbrowser import launch
            from bs4 import BeautifulSoup
        except ImportError:
            return []
        browser = None
        try:
            browser = launch(headless=True)
            page = browser.new_page()
            page.goto(_URL, timeout=45000)
            page.wait_for_selector("div.listing", timeout=20000)
            html = page.content()
        except Exception:
            return []
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        events: list[RawEvent] = []

        for el in soup.select("div.listing"):
            try:
                dt = _parse_date(el)
                if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                    continue

                title_el = el.select_one("h2.listing__title")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                btn = el.select_one("[data-show-event-url]")
                ticket_url = btn["data-show-event-url"] if btn else None

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt, title),
                    source_url=ticket_url or _URL,
                    title=title,
                    date_start_utc=dt,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=_CFG["genres"],
                    ticket_url=ticket_url,
                    raw_payload={},
                ))
            except Exception:
                continue
        return events
