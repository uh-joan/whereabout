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

_CFG = load_venue_config("venue_southbank_centre")
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

_MUSIC_ARTFORMS = {
    "classical music", "gigs", "jazz", "folk", "world music",
    "contemporary music", "music", "opera",
}

_ARTFORM_GENRES: dict[str, list[str]] = {
    "classical music": ["classical", "orchestral", "chamber"],
    "gigs": ["world", "jazz", "soul", "contemporary"],
    "jazz": ["jazz"],
    "folk": ["folk", "acoustic", "world"],
    "world music": ["world", "afrobeat"],
    "contemporary music": ["contemporary", "experimental"],
    "opera": ["opera", "classical"],
}

_TIME_RE = re.compile(r",\s*(\d{1,2}(?:\.\d{2})?(?:am|pm))\s*$", re.IGNORECASE)
_YEAR_RE = re.compile(r"\d{4}")


def _parse_date(date_text: str) -> datetime | None:
    text = date_text.strip()
    # Extract time suffix: ", 6pm" or ", 4.30pm"
    time_m = _TIME_RE.search(text)
    hour, minute = _DEFAULT_HOUR, _DEFAULT_MIN
    if time_m:
        t_str = time_m.group(1).upper()
        try:
            t = datetime.strptime(t_str, "%I.%M%p") if "." in t_str else datetime.strptime(t_str, "%I%p")
            hour, minute = t.hour, t.minute
        except ValueError:
            pass
        text = text[: time_m.start()].strip()

    # Take start of range: split on "–" or "&"
    start_part = re.split(r"[–&]", text)[0].strip()
    end_part = re.split(r"[–&]", text)[-1].strip()

    # Get year — prefer from start_part, fall back to end_part
    year_m = _YEAR_RE.search(start_part) or _YEAR_RE.search(end_part)
    year = int(year_m.group()) if year_m else datetime.now().year

    # Strip year from start_part if present, rebuild without it for parsing
    start_clean = _YEAR_RE.sub("", start_part).strip()

    try:
        naive = datetime.strptime(f"{start_clean} {year}", "%a %d %b %Y")
        return naive.replace(hour=hour, minute=minute)
    except ValueError:
        return None


class SouthbankCentreSource(BaseSource):
    source_id = "venue_southbank_centre"
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
        seen: set[str] = set()
        events: list[RawEvent] = []

        for card in soup.select("div.c-event-card"):
            try:
                content = card.select_one("div.c-event-card__content")
                if not content:
                    continue

                artform_el = content.select_one(".c-event-card__primary-artform")
                artform = artform_el.get_text(strip=True).lower() if artform_el else ""
                if artform not in _MUSIC_ARTFORMS:
                    continue

                h3 = content.select_one("h3.c-event-card__title")
                if not h3:
                    continue
                title = h3.get_text(strip=True)

                time_el = content.select_one("time.c-event-card__daterange")
                if not time_el:
                    continue
                naive = _parse_date(time_el.get_text(strip=True))
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

                link = card.select_one("a[href]")
                source_url = link["href"] if link else _URL
                genres = _ARTFORM_GENRES.get(artform, _CFG["genres"])

                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=event_id,
                    source_url=source_url,
                    title=title,
                    date_start_utc=dt_utc,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=genres,
                    ticket_url=source_url,
                    raw_payload={},
                ))
            except Exception:
                continue

        return events
