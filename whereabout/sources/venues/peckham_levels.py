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

_CFG = load_venue_config("venue_peckham_levels")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}

_MUSIC_TITLE = re.compile(
    r"\bdj\b|selector|live music|open mic|jazz|soul|electronic|gig|band|concert|disco|funk|rave|club night",
    re.IGNORECASE,
)
_MUSIC_CAT = re.compile(r"live music", re.IGNORECASE)
_SKIP_TITLE = re.compile(r"chess|quiz|karaoke|comedy|workshop|talk|cabaret|theatre|film|book club", re.IGNORECASE)
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


class PeckhamLevelsSource(BaseSource):
    source_id = "venue_peckham_levels"
    freshness_seconds = 3 * 3600

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

        for art in soup.select("article.eventlist-event--upcoming"):
            try:
                title_el = art.select_one(".eventlist-title-link") or art.select_one(".eventlist-title")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                cat_el = art.select_one(".eventlist-cats")
                cat_text = cat_el.get_text(strip=True) if cat_el else ""
                if not _MUSIC_TITLE.search(title) and not _MUSIC_CAT.search(cat_text):
                    continue
                if _SKIP_TITLE.search(title):
                    continue

                date_el = art.select_one("time.event-date[datetime]")
                if not date_el:
                    continue
                date_str = date_el.get("datetime", "")
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                    continue

                time_el = art.select_one(".eventlist-meta-time")
                hour, minute = _DEFAULT_HOUR, _DEFAULT_MIN
                if time_el:
                    m = _TIME_RE.match(time_el.get_text(strip=True))
                    if m:
                        hour, minute = int(m.group(1)), int(m.group(2))

                naive = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour, minute=minute)
                local = naive.replace(tzinfo=_LONDON_TZ)
                dt_utc = local.astimezone(timezone.utc)

                if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                    continue

                event_id = venue_event_id(_POSTCODE, dt_utc, title)
                if event_id in seen:
                    continue
                seen.add(event_id)

                link_el = art.select_one("a.eventlist-title-link[href]")
                href = link_el["href"] if link_el else ""
                source_url = f"https://www.peckhamlevels.org{href}" if href.startswith("/") else (href or _URL)

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
