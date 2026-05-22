from __future__ import annotations
import hashlib
from datetime import datetime


def venue_event_id(postcode: str, dt_utc: datetime, title: str) -> str:
    key = f"{postcode}|{dt_utc.strftime('%Y%m%dT%H%M')}|{title.lower().strip()}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]
