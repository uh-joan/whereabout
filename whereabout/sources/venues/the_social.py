from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_the_social")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_DEFAULT_HOUR, _DEFAULT_MIN = map(int, _CFG["default_time"].split(":"))
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}


def _parse_start_date(dt_str: str) -> datetime | None:
    """Parse JSON-LD startDate, e.g. '2026-05-27T18:00' or '2026-05-27'."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            naive = datetime.strptime(dt_str, fmt)
            if fmt == "%Y-%m-%d":
                naive = naive.replace(hour=_DEFAULT_HOUR, minute=_DEFAULT_MIN)
            return naive.replace(tzinfo=_LONDON_TZ).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _extract_events_from_jsonld(soup: BeautifulSoup) -> list[dict]:
    """Extract all schema.org Event objects from JSON-LD script tags."""
    events: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "Event":
                    events.append(item)
        elif isinstance(data, dict):
            if data.get("@type") == "Event":
                events.append(data)
            for item in data.get("@graph", []):
                if isinstance(item, dict) and item.get("@type") == "Event":
                    events.append(item)
    return events


class TheSocialSource(BaseSource):
    source_id = "venue_the_social"
    freshness_seconds = 2 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        try:
            r = httpx.get(_URL, headers=_HEADERS, timeout=10, follow_redirects=True)
            r.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        raw_events = _extract_events_from_jsonld(soup)
        events: list[RawEvent] = []

        for item in raw_events:
            title = BeautifulSoup(item.get("name", ""), "html.parser").get_text(strip=True)
            if not title:
                continue

            start_str = item.get("startDate", "")
            dt = _parse_start_date(start_str)
            if not dt:
                continue

            if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                continue

            event_url = item.get("url", _URL)

            events.append(RawEvent(
                source=self.source_id,
                source_event_id=venue_event_id(_POSTCODE, dt, title),
                source_url=event_url,
                title=title,
                date_start_utc=dt,
                venue_name=_VENUE,
                venue_postcode=_POSTCODE,
                genres_raw=_CFG["genres"],
                ticket_url=event_url,
                raw_payload={},
            ))

        return events
