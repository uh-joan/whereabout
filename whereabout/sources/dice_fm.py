from __future__ import annotations
import hashlib
import json
import httpx
from datetime import datetime, timezone
from pathlib import Path

from whereabout.models import RawEvent, Query
from whereabout.sources.base import BaseSource

CACHE_DIR = Path.home() / ".cache" / "whereabout" / "dice-response-cache"
SNAPSHOT_DIR = Path.home() / ".cache" / "whereabout" / "source-snapshots" / "dice"
CACHE_TTL_SECONDS = 300  # 5 minutes

# Public API key embedded in the DICE web app
_API_KEY = "7vYeaK9Zfi9aC94moLEF88rfLtnhicFH1q1Mb5Q8"

# DICE city IDs for UK cities
_CITY_IDS = {
    "london": "54d8a23438fe5d27d500001c",
    "manchester": "54d8a22538fe5d27d5000019",
    "birmingham": "56430c071b1e7311084a134d",
    "brighton": "5665ad1ae3ff13adb15e0ca6",
    "bristol": "54d8a21638fe5d27d5000016",
    "edinburgh": "5e426532749e68e3e923d1dd",
    "glasgow": "54d8a20238fe5d27d5000013",
    "leeds": "55f0381d5e0c39b48e8928fd",
    "liverpool": "560e9ed74053e1fcd2f0080e",
    "sheffield": "5744619e6bc0a48a3d4c676b",
}
_DEFAULT_CITY_ID = _CITY_IDS["london"]


class DICESource(BaseSource):
    source_id = "dice_fm"
    BASE_URL = "https://events-api.dice.fm/v1/events"

    async def fetch(self, query: Query) -> list[RawEvent]:
        params = self._build_params(query)
        cache_key = hashlib.sha256(
            json.dumps(params, sort_keys=True).encode()
        ).hexdigest()[:16]

        cached = self._load_cache(cache_key)
        if cached is not None:
            return self._parse_response(cached)

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(
                self.BASE_URL,
                params=params,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; whereabout/0.1)",
                    "x-api-key": _API_KEY,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        self._save_cache(cache_key, data)
        self._save_snapshot(data)
        return self._parse_response(data)

    def _build_params(self, query: Query) -> dict:
        city_id = _DEFAULT_CITY_ID
        params: dict = {
            "filter[city_ids][]": city_id,
            "page[size]": "100",
            "filter[from_date]": query.date_range_start_utc.strftime("%Y-%m-%d"),
            "filter[to_date]": query.date_range_end_utc.strftime("%Y-%m-%d"),
        }
        return params

    def _parse_response(self, data: dict | list) -> list[RawEvent]:
        events = []
        if isinstance(data, list):
            items = data
        else:
            items = data.get("data") or []
        for item in items:
            try:
                events.append(self._parse_event(item))
            except Exception:
                continue
        return events

    def _parse_event(self, item: dict) -> RawEvent:
        date_str = item.get("date") or item.get("start_date", "")
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)

        artists = [a["name"] for a in item.get("artists", []) if a.get("name")]
        genres = item.get("genre_tags") or item.get("genres", []) or item.get("tags", [])

        ticket_types = item.get("ticket_types", [])
        price_text = None
        if ticket_types:
            price = ticket_types[0].get("price", {})
            total = price.get("total", 0)
            if total:
                price_text = f"£{total / 100:.0f}"

        location = item.get("location") or {}
        venues_list = item.get("venues") or []
        venue_name = venues_list[0]["name"] if venues_list else item.get("venue", "")

        return RawEvent(
            source="dice_fm",
            source_event_id=str(item.get("id", "")),
            source_url=item.get("url", ""),
            title=item.get("name", ""),
            date_start_utc=dt,
            venue_name=venue_name,
            venue_address=item.get("address"),
            venue_postcode=location.get("zip"),
            venue_lat=location.get("lat"),
            venue_lng=location.get("lng"),
            artists=artists,
            genres_raw=genres,
            ticket_url=item.get("url"),
            price_text=price_text,
            raw_payload=item,
        )

    def _load_cache(self, key: str) -> dict | None:
        path = CACHE_DIR / f"{key}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        cached_at = data.get("_cached_at", 0)
        if datetime.now(timezone.utc).timestamp() - cached_at > CACHE_TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None
        return data.get("payload")

    def _save_cache(self, key: str, data: dict) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        wrapper = {
            "_cached_at": datetime.now(timezone.utc).timestamp(),
            "payload": data,
        }
        (CACHE_DIR / f"{key}.json").write_text(json.dumps(wrapper))

    def _save_snapshot(self, data: dict) -> None:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (SNAPSHOT_DIR / f"{ts}.json").write_text(json.dumps(data, indent=2))
