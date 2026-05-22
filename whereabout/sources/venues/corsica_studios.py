from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id

_URL = "https://www.corsicastudios.com/events/"
_POSTCODE = "SE17 1LB"
_VENUE = "Corsica Studios"
_LONDON_TZ = ZoneInfo("Europe/London")


class CorsicaStudiosSource(BaseSource):
    source_id = "venue_corsica_studios"
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
            page.goto(_URL, timeout=30000)
            page.wait_for_selector(".event, .event-item, article, .listing", timeout=10000)
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
        events = []
        for el in soup.select(".event, .event-item, article, .listing"):
            try:
                title_el = el.select_one("h2, h3, .event-title, .title")
                date_el = el.select_one("time, .date, .event-date")
                link_el = el.select_one("a[href]")
                if not title_el or not date_el:
                    continue
                title = title_el.get_text(strip=True)
                date_str = date_el.get("datetime") or date_el.get_text(strip=True)
                ticket_url = link_el.get("href") if link_el else None
                if ticket_url and ticket_url.startswith("/"):
                    ticket_url = "https://www.corsicastudios.com" + ticket_url
                try:
                    if "T" in date_str or "Z" in date_str:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=_LONDON_TZ).astimezone(timezone.utc)
                    else:
                        naive = datetime.strptime(date_str[:10], "%Y-%m-%d")
                        dt = naive.replace(hour=20, tzinfo=_LONDON_TZ).astimezone(timezone.utc)
                except Exception:
                    continue
                if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                    continue
                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt, title),
                    source_url=ticket_url or _URL,
                    title=title,
                    date_start_utc=dt,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=["electronic"],
                    ticket_url=ticket_url,
                    raw_payload={},
                ))
            except Exception:
                continue
        return events
