from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from whereabout.models import Query, RawEvent, Event, Venue, Artist
from whereabout.sources.dice_fm import DICESource
from whereabout.sources.resident_advisor import RASource
from whereabout import neighbourhoods as nb
from whereabout.kb.ingest import ingest
from whereabout.kb.read import read_events_for_range

_GENRE_ALIASES: dict[str, list[str]] = json.loads(
    (Path(__file__).parent.parent / "data" / "genre_aliases.json").read_text()
)

def _expand_genres(genres: list[str]) -> set[str]:
    expanded: set[str] = set()
    for g in genres:
        gl = g.lower()
        expanded.add(gl)
        for alias in _GENRE_ALIASES.get(gl, []):
            expanded.add(alias.lower())
    return expanded


def _date_key(query: Query) -> str:
    return f"{query.date_range_start_utc.date()}|{query.date_range_end_utc.date()}"


def _is_stale(source_id: str, date_key: str, freshness_seconds: int) -> bool:
    from whereabout.db import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT fetched_at FROM source_fetches WHERE source_id = ? AND date_key = ?",
            (source_id, date_key),
        ).fetchone()
    if row is None:
        return True
    return (datetime.now(timezone.utc).timestamp() - row["fetched_at"]) > freshness_seconds


def _mark_fetched(source_id: str, date_key: str) -> None:
    from whereabout.db import get_connection
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO source_fetches(source_id, date_key, fetched_at) VALUES (?, ?, ?)",
            (source_id, date_key, datetime.now(timezone.utc).timestamp()),
        )
        conn.commit()


async def _fetch_all(query: Query, force: bool = False) -> list[RawEvent]:
    """Fetch from stale live sources only; ingest results and return fetched raws.

    Returns the list of RawEvents fetched this call. If all sources are fresh,
    returns an empty list (caller should read from KB instead).
    """
    from whereabout.sources.venues import ALL_VENUE_SOURCES
    from whereabout.sources.songkick import SongkickSource
    date_key = _date_key(query)
    all_sources = [DICESource(), RASource(), SongkickSource()] + ALL_VENUE_SOURCES
    live_sources = [s for s in all_sources if getattr(s, "live", True)]
    if force:
        stale = live_sources
    else:
        stale = [s for s in live_sources if _is_stale(s.source_id, date_key, s.freshness_seconds)]
    if not stale:
        return []
    results = await asyncio.gather(*[s.fetch(query) for s in stale], return_exceptions=True)
    raws: list[RawEvent] = []
    for s, r in zip(stale, results):
        if isinstance(r, list):
            raws.extend(r)
            _mark_fetched(s.source_id, date_key)
    if raws:
        ingest(raws)
    return raws


def rank(query: Query, force: bool = False) -> list[dict]:
    """
    Fetch from stale live sources, filter by neighbourhood, sort by date.
    When sources are fresh, reads from KB. Otherwise uses freshly fetched raws.
    Returns list of dicts ready for list_view rendering.
    """
    asyncio.run(_fetch_all(query, force=force))
    # Always read from KB — includes both live-fetched and scheduled (browser) sources
    raws = read_events_for_range(query.date_range_start_utc, query.date_range_end_utc)

    # Always enforce neighbourhood — hyperlocal only, no generic "London" events
    raws = _filter_by_neighbourhood(raws, query.neighbourhood)

    # Filter by genre if specified
    if query.genres:
        raws = _filter_by_genre(raws, query.genres)

    # Filter to date range
    raws = [r for r in raws
            if query.date_range_start_utc <= r.date_start_utc <= query.date_range_end_utc]

    # Dedup cross-source duplicates: same venue + same start time → keep the one with more artists
    seen: dict[tuple, RawEvent] = {}
    for raw in raws:
        key = (raw.venue_postcode or raw.venue_name, raw.date_start_utc)
        existing = seen.get(key)
        if existing is None or len(raw.artists) > len(existing.artists):
            seen[key] = raw
    raws = list(seen.values())

    # Sort by date ascending
    raws.sort(key=lambda r: r.date_start_utc)

    return [_to_result_dict(r, i + 1) for i, r in enumerate(raws[:query.limit])]


def _filter_by_neighbourhood(raws: list[RawEvent], neighbourhood: str | None) -> list[RawEvent]:
    result = []
    for raw in raws:
        if not raw.venue_postcode:
            continue
        resolved = nb.resolve_postcode_prefix(raw.venue_postcode)
        if not resolved:
            continue
        if neighbourhood is None or resolved.lower() == neighbourhood.lower():
            result.append(raw)
    return result


def _filter_by_genre(raws: list[RawEvent], genres: list[str]) -> list[RawEvent]:
    genre_set = _expand_genres(genres)
    result = []
    for raw in raws:
        # Strip DICE namespace prefixes (e.g. "gig:jazz" → "jazz") before comparing
        raw_genres = {
            g.lower().split(":")[-1] if ":" in g.lower() else g.lower()
            for g in raw.genres_raw
        }
        if raw_genres & genre_set:
            result.append(raw)
    return result


_FESTIVAL_VENUE_KEYWORDS = {"park", "common", "fields", "ground", "racecourse", "arena"}


def _is_festival(raw: RawEvent) -> bool:
    if raw.is_festival:
        return True
    venue_lower = (raw.venue_name or "").lower()
    if any(kw in venue_lower for kw in _FESTIVAL_VENUE_KEYWORDS):
        return True
    if len(raw.artists) >= 6:
        return True
    return False


def _to_result_dict(raw: RawEvent, index: int) -> dict:
    from zoneinfo import ZoneInfo
    from whereabout.kb.ingest import stable_hash
    local_dt = raw.date_start_utc.astimezone(ZoneInfo("Europe/London"))
    return {
        "index": index,
        "title": raw.title,
        "artists": raw.artists,
        "venue": raw.venue_name,
        "postcode": raw.venue_postcode or "",
        "date_local": local_dt.strftime("%a %d %b"),
        "time_local": local_dt.strftime("%H:%M"),
        "genres": raw.genres_raw,
        "ticket_url": raw.ticket_url,
        "price": raw.price_text or "TBC",
        "source": raw.source,
        "source_event_id": raw.source_event_id,
        "stable_hash": stable_hash(raw),
        "is_festival": _is_festival(raw),
    }
