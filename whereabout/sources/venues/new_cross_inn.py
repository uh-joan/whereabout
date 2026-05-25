from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource
from whereabout.sources.venues._utils import venue_event_id, load_venue_config

_CFG = load_venue_config("venue_new_cross_inn")
_URL = _CFG["url"]
_POSTCODE = _CFG["postcode"]
_VENUE = _CFG["name"]
_LONDON_TZ = ZoneInfo("Europe/London")


def _parse_nci_date(text: str) -> datetime | None:
    # "25 May 2026 @ 18:00"
    try:
        return datetime.strptime(text.strip(), "%d %B %Y @ %H:%M")
    except ValueError:
        return None


class NewCrossInnSource(BaseSource):
    source_id = "venue_new_cross_inn"
    live = True
    freshness_seconds = 3 * 3600

    async def fetch(self, query: Query) -> list[RawEvent]:
        try:
            async with httpx.AsyncClient(
                timeout=15, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"}
            ) as client:
                r = await client.get(_URL)
            r.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        events: list[RawEvent] = []
        seen: set[str] = set()

        for li in soup.select("li.col-span-1"):
            try:
                title_el = li.select_one(".nci-event-name")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title:
                    continue

                flex_div = li.select_one(".flex-1")
                if not flex_div:
                    continue
                texts = [t.strip() for t in flex_div.get_text(separator="\n").split("\n") if t.strip()]
                date_text = next((t for t in texts if "@" in t), None)
                if not date_text:
                    continue

                naive = _parse_nci_date(date_text)
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

                link_el = li.find("a", href=True)
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
            except Exception:
                continue

        return events
