from __future__ import annotations
import hashlib
from datetime import datetime


def venue_event_id(postcode: str, dt_utc: datetime, title: str) -> str:
    key = f"{postcode}|{dt_utc.strftime('%Y%m%dT%H%M')}|{title.lower().strip()}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def load_venue_config(source_id: str) -> dict:
    import json
    from importlib.resources import files
    data = json.loads(files("whereabout.data").joinpath("venues.json").read_text())
    for v in data:
        if v["source_id"] == source_id:
            return v
    raise KeyError(f"No venue config for {source_id!r}")
