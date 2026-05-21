from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource

CACHE_DIR = Path.home() / ".cache" / "whereabout" / "ra-response-cache"
SNAPSHOT_DIR = Path.home() / ".cache" / "whereabout" / "source-snapshots" / "ra"
CACHE_TTL_SECONDS = 300  # 5 minutes
PAGE_SIZE = 100
MAX_PAGES = 5  # cap at 500 events per query

_LONDON_AREA_ID = 13
_LONDON_TZ = ZoneInfo("Europe/London")

# Matches UK postcodes anywhere in an address string
_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2})\b")
_LINEUP_TAG_RE = re.compile(r"<artist[^>]*>([^<]+)</artist>", re.IGNORECASE)
_LINEUP_SPLIT_RE = re.compile(r"\s*(?:,\s*|&amp;|&|\sb2b\s|\s\+\s|\svs\.?\s|\s/\s)\s*", re.IGNORECASE)
_PAREN_RE = re.compile(r"\s*\([^)]*\)")

_GRAPHQL_URL = "https://ra.co/graphql"
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Referer": "https://ra.co/",
    "Origin": "https://ra.co",
}

_EVENTS_QUERY = """
query GET_EVENT_LISTINGS($filters: FilterInputDtoInput, $pageSize: Int, $page: Int) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page) {
    data {
      id
      listingDate
      event {
        id
        title
        startTime
        endTime
        cost
        contentUrl
        lineup
        isTicketed
        venue {
          id
          name
          address
          area { id name }
        }
        artists { id name }
        genres { id name }
      }
    }
    totalResults
  }
}
"""


def _parse_lineup(lineup: str) -> list[str]:
    """Extract artist names from RA lineup field (XML tags or plain text)."""
    tagged = _LINEUP_TAG_RE.findall(lineup)
    if tagged:
        return [n.strip() for n in tagged if n.strip()]
    # Plain text: split on common separators, strip parentheticals
    parts = _LINEUP_SPLIT_RE.split(lineup)
    names = []
    for part in parts:
        name = _PAREN_RE.sub("", part).strip()
        if name:
            names.append(name)
    return names


def _extract_postcode(address: str) -> str | None:
    m = _POSTCODE_RE.search(address.upper())
    if m:
        # normalise: strip internal spaces, add canonical space before inward code
        raw = m.group(1).replace(" ", "")
        return raw[:-3] + " " + raw[-3:]
    return None


def _parse_local_dt(dt_str: str) -> datetime:
    # RA returns LocalDateTime like "2026-05-21T19:00:00.000" — treat as London local
    dt_str = dt_str.split(".")[0]  # strip milliseconds
    naive = datetime.fromisoformat(dt_str)
    local = naive.replace(tzinfo=_LONDON_TZ)
    return local.astimezone(timezone.utc)



class RASource(BaseSource):
    source_id = "resident_advisor"

    async def fetch(self, query: Query) -> list[RawEvent]:
        cache_key = self._cache_key(query)
        cached = self._load_cache(cache_key)
        if cached is not None:
            return [self._parse_listing(l) for l in cached]

        listings = await self._fetch_all(query)
        self._save_cache(cache_key, listings)
        self._save_snapshot(listings)
        return [self._parse_listing(l) for l in listings]

    async def _fetch_all(self, query: Query) -> list[dict]:
        filters = {
            "areas": {"eq": _LONDON_AREA_ID},
            "listingDate": {
                "gte": query.date_range_start_utc.strftime("%Y-%m-%d"),
                "lte": query.date_range_end_utc.strftime("%Y-%m-%d"),
            },
            "listingPosition": 1,
        }
        all_listings: list[dict] = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for page in range(1, MAX_PAGES + 1):
                payload = {
                    "query": _EVENTS_QUERY,
                    "variables": {"filters": filters, "pageSize": PAGE_SIZE, "page": page},
                }
                resp = await client.post(_GRAPHQL_URL, json=payload, headers=_BROWSER_HEADERS)
                resp.raise_for_status()
                data = resp.json()
                if "errors" in data:
                    raise RuntimeError(f"RA GraphQL error: {data['errors'][0]['message']}")
                result = data["data"]["eventListings"]
                batch = result.get("data") or []
                all_listings.extend(batch)
                if len(all_listings) >= result.get("totalResults", 0):
                    break
        return all_listings

    def _parse_listing(self, listing: dict) -> RawEvent:
        ev = listing.get("event") or {}
        venue = ev.get("venue") or {}
        address = venue.get("address") or ""

        start_raw = ev.get("startTime") or ev.get("listingDate") or ""
        end_raw = ev.get("endTime")
        dt_start = _parse_local_dt(start_raw) if start_raw else datetime.now(timezone.utc)
        dt_end = _parse_local_dt(end_raw) if end_raw else None

        postcode = _extract_postcode(address)
        artists = [a["name"] for a in (ev.get("artists") or []) if a.get("name")]
        if not artists and ev.get("lineup"):
            artists = _parse_lineup(ev["lineup"])
        genres = [g["name"] for g in (ev.get("genres") or []) if g.get("name")]

        # content_url is a relative path like "/events/uk/london/venue/..."
        content_url = ev.get("contentUrl") or ""
        source_url = f"https://ra.co{content_url}" if content_url.startswith("/") else content_url

        cost = ev.get("cost") or ""
        price_text = cost.strip() or None

        return RawEvent(
            source="resident_advisor",
            source_event_id=str(ev.get("id") or listing.get("id") or ""),
            source_url=source_url,
            title=ev.get("title") or "",
            date_start_utc=dt_start,
            date_end_utc=dt_end,
            venue_name=venue.get("name") or "",
            venue_address=address or None,
            venue_postcode=postcode,
            artists=artists,
            genres_raw=genres,
            ticket_url=source_url or None,
            price_text=price_text,
            raw_payload=listing,
        )

    def _cache_key(self, query: Query) -> str:
        key = f"{query.date_range_start_utc.date()}|{query.date_range_end_utc.date()}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _load_cache(self, key: str) -> list[dict] | None:
        path = CACHE_DIR / f"{key}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        cached_at = data.get("_cached_at", 0)
        if datetime.now(timezone.utc).timestamp() - cached_at > CACHE_TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None
        return data.get("payload")

    def _save_cache(self, key: str, listings: list[dict]) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        wrapper = {
            "_cached_at": datetime.now(timezone.utc).timestamp(),
            "payload": listings,
        }
        (CACHE_DIR / f"{key}.json").write_text(json.dumps(wrapper))

    def _save_snapshot(self, listings: list[dict]) -> None:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (SNAPSHOT_DIR / f"{ts}.json").write_text(json.dumps(listings, indent=2))
