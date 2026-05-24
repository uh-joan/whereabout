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

_CFG = load_venue_config("venue_cecil_sharp_house")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_LONDON_TZ = ZoneInfo("Europe/London")
_HEADERS = {"User-Agent": "whereabout/1.0 +github.com/uh-joan/whereabout"}

# Catids for music events only: 26=Gigs, 73=Folk Club
_MUSIC_CATIDS = {26, 73}

# eventTimes key format: "20260526193000" -> YYYYMMDDHHmmss
_DT_KEY_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$")

# JS single-quoted string decoder
def _decode_js_str(s: str) -> str:
    result: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            c = s[i + 1]
            if c == "'":
                result.append("'"); i += 2
            elif c == '"':
                result.append('"'); i += 2
            elif c == "\\":
                result.append("\\"); i += 2
            elif c == "n":
                result.append("\n"); i += 2
            elif c == "r":
                result.append("\r"); i += 2
            else:
                result.append(s[i]); i += 1
        else:
            result.append(s[i]); i += 1
    return "".join(result)


class CecilSharpHouseSource(BaseSource):
    source_id = "venue_cecil_sharp_house"
    freshness_seconds = 3 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        return await asyncio.to_thread(self._fetch_sync, query)

    def _fetch_sync(self, query: Query) -> list[RawEvent]:
        import json

        try:
            r = httpx.get(_URL, headers=_HEADERS, timeout=10, follow_redirects=True)
            r.raise_for_status()
        except Exception:
            return []

        # Extract embedded JS JSON array
        match = re.search(r"var eeVents = '(.+?)';", r.text, re.DOTALL)
        if not match:
            return []

        try:
            raw_events = json.loads(_decode_js_str(match.group(1)))
        except Exception:
            return []

        events: list[RawEvent] = []

        for ev in raw_events:
            if ev.get("catid") not in _MUSIC_CATIDS:
                continue

            # eventTimes may contain multiple occurrences; emit one RawEvent per time slot
            event_times = ev.get("eventTimes", {})
            if not event_times:
                # Fall back to firstEventDigits
                date_str = ev.get("firstEventDigits", "")
                if not date_str:
                    continue
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
                        hour=19, minute=30, tzinfo=_LONDON_TZ
                    ).astimezone(timezone.utc)
                except ValueError:
                    continue
                slots = [(dt, None)]
            else:
                slots = []
                for key, slot in event_times.items():
                    m = _DT_KEY_RE.match(key)
                    if not m:
                        continue
                    try:
                        dt = datetime(
                            int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            int(m.group(4)), int(m.group(5)), int(m.group(6)),
                            tzinfo=_LONDON_TZ,
                        ).astimezone(timezone.utc)
                    except ValueError:
                        continue
                    end_str = slot.get("end", "")
                    dt_end = None
                    if end_str:
                        try:
                            end_norm = end_str.replace(".", ":").upper()
                            end_time = datetime.strptime(end_norm, "%I:%M%p")
                            dt_end = dt.replace(
                                hour=end_time.hour, minute=end_time.minute, second=0
                            )
                        except ValueError:
                            pass
                    slots.append((dt, dt_end))

            title = ev.get("title", "").strip()
            link = ev.get("link", "")
            event_url = f"https://www.efdss.org{link}" if link else _URL
            booking_url = ev.get("bookingLink") or event_url

            for dt, dt_end in slots:
                if not (query.date_range_start_utc <= dt <= query.date_range_end_utc):
                    continue
                events.append(RawEvent(
                    source=self.source_id,
                    source_event_id=venue_event_id(_POSTCODE, dt, title),
                    source_url=event_url,
                    title=title,
                    date_start_utc=dt,
                    date_end_utc=dt_end,
                    venue_name=_VENUE,
                    venue_postcode=_POSTCODE,
                    genres_raw=_CFG["genres"],
                    ticket_url=booking_url or event_url,
                    raw_payload={"catid": ev.get("catid"), "id": ev.get("id")},
                ))

        return events
