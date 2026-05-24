from __future__ import annotations
import asyncio
import re
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_moth_club")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_LONDON_TZ = ZoneInfo("Europe/London")

# DICE widget date text: "Sun 24 May ― 11:00pm"
_DATE_SPLIT_RE = re.compile(r"\s*[―—–]\s*")
_SKIP_RE = re.compile(r"\bcomedy\b|\bquiz\b|\bbingo\b|\bkaraoke\b|\bstandup\b|\bstand.up\b", re.IGNORECASE)


def _parse_dice_datetime(time_text: str) -> datetime:
    parts = _DATE_SPLIT_RE.split(time_text.strip(), maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"Unexpected date format: {time_text!r}")
    date_str, time_str = parts[0].strip(), parts[1].strip().upper()
    # "%a %d %b" → e.g. "Sun 24 May"
    parsed = datetime.strptime(date_str, "%a %d %b")
    t = datetime.strptime(time_str, "%I:%M%p")
    today = date.today()
    year = today.year
    # advance year if the date has already passed
    candidate = parsed.replace(year=year, hour=t.hour, minute=t.minute)
    if candidate.date() < today:
        candidate = candidate.replace(year=year + 1)
    return candidate


class MothClubSource(BaseSource):
    source_id = "venue_moth_club"
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
            time_el = art.find("time")
            if not time_el:
                continue
            try:
                naive = _parse_dice_datetime(time_el.get_text(strip=True))
            except Exception:
                continue

            img = art.find("img", alt=True)
            if not img or not img["alt"].strip():
                continue
            title = img["alt"].strip()
            if _SKIP_RE.search(title):
                continue

            local = naive.replace(tzinfo=_LONDON_TZ)
            dt_utc = local.astimezone(timezone.utc)
            if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                continue

            event_id = venue_event_id(_POSTCODE, dt_utc, title)
            if event_id in seen:
                continue
            seen.add(event_id)

            link_el = art.find("a", href=re.compile(r"dice\.fm"))
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

        return events
