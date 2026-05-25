from __future__ import annotations
import html as html_mod
import re
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_EVENTS_RE = re.compile(
    r"sessionStorage\.setItem\('whatsonEvents',\s*JSON\.stringify\((\{.*?\})\)\s*\);",
    re.DOTALL,
)
_LONDON_TZ = ZoneInfo("Europe/London")


def _parse_bk_event(e: dict) -> datetime | None:
    date_str = e.get("event_date", "")
    time_str = e.get("start_time", "")
    if not date_str or not time_str:
        return None
    try:
        combined = f"{date_str} {time_str.upper()}"
        naive = datetime.strptime(combined, "%d/%m/%Y %I:%M %p")
        return naive.replace(tzinfo=_LONDON_TZ).astimezone(timezone.utc)
    except ValueError:
        return None


class _BluesKitchenBase(BaseSource):
    live = True
    freshness_seconds = 3 * 3600
    _cfg_key: str

    def __init__(self) -> None:
        cfg = load_venue_config(self._cfg_key)
        self._url = cfg["url"]
        self._postcode = cfg["postcode"]
        self._venue = cfg["name"]
        self._genres = cfg["genres"]

    async def fetch(self, query: Query) -> list[RawEvent]:
        try:
            async with httpx.AsyncClient(
                timeout=15, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"}
            ) as client:
                r = await client.get(self._url)
            r.raise_for_status()
        except Exception:
            return []

        match = _EVENTS_RE.search(r.text)
        if not match:
            return []

        try:
            data = json.loads(match.group(1))
        except Exception:
            return []

        events: list[RawEvent] = []
        seen: set[str] = set()

        for year_data in data.values():
            for month_events in year_data.values():
                for e in month_events:
                    try:
                        title = html_mod.unescape(e.get("event_name") or "").strip()
                        if not title:
                            continue
                        dt_utc = _parse_bk_event(e)
                        if dt_utc is None:
                            continue
                        if not (query.date_range_start_utc <= dt_utc <= query.date_range_end_utc):
                            continue
                        event_id = venue_event_id(self._postcode, dt_utc, title)
                        if event_id in seen:
                            continue
                        seen.add(event_id)
                        source_url = e.get("permalink") or self._url
                        events.append(RawEvent(
                            source=self.source_id,
                            source_event_id=event_id,
                            source_url=source_url,
                            title=title,
                            date_start_utc=dt_utc,
                            venue_name=self._venue,
                            venue_postcode=self._postcode,
                            genres_raw=self._genres,
                            ticket_url=source_url,
                            raw_payload={},
                        ))
                    except Exception:
                        continue

        return events


class BluesKitchenCamdenSource(_BluesKitchenBase):
    source_id = "venue_blues_kitchen_camden"
    _cfg_key = "venue_blues_kitchen_camden"


class BluesKitchenShoreditchSource(_BluesKitchenBase):
    source_id = "venue_blues_kitchen_shoreditch"
    _cfg_key = "venue_blues_kitchen_shoreditch"


class BluesKitchenBrixtonSource(_BluesKitchenBase):
    source_id = "venue_blues_kitchen_brixton"
    _cfg_key = "venue_blues_kitchen_brixton"
