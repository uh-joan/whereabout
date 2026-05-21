"""postcodes.io client — returns lat/lng only. Ward names are NOT used."""
from __future__ import annotations
import json
from pathlib import Path
import httpx

CACHE_PATH = Path.home() / ".cache" / "whereabout" / "postcodes.json"


def lookup_latlong(postcode: str) -> tuple[float, float] | None:
    """Return (lat, lng) for a UK postcode, or None if not found."""
    normalised = postcode.upper().replace(" ", "")
    # Check cache
    cache = _load_cache()
    if normalised in cache:
        entry = cache[normalised]
        if entry is None:
            return None
        return entry["lat"], entry["lng"]
    # Fetch from postcodes.io
    try:
        resp = httpx.get(f"https://api.postcodes.io/postcodes/{normalised}", timeout=5.0)
        if resp.status_code == 200:
            result = resp.json()["result"]
            entry = {"lat": result["latitude"], "lng": result["longitude"]}
        else:
            entry = None
    except Exception:
        return None
    cache[normalised] = entry
    _save_cache(cache)
    if entry is None:
        return None
    return entry["lat"], entry["lng"]


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2))
