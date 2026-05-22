from __future__ import annotations
import asyncio
import json
from pathlib import Path
from whereabout.models import Query, RawEvent, Event, Venue, Artist
from whereabout.sources.dice_fm import DICESource
from whereabout.sources.resident_advisor import RASource
from whereabout import neighbourhoods as nb
from whereabout.kb.ingest import ingest

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


async def _fetch_all(query: Query) -> list[RawEvent]:
    from whereabout.sources.venues import ALL_VENUE_SOURCES
    sources = [DICESource(), RASource()] + ALL_VENUE_SOURCES
    results = await asyncio.gather(*[s.fetch(query) for s in sources], return_exceptions=True)
    raws: list[RawEvent] = []
    for r in results:
        if isinstance(r, list):
            raws.extend(r)
    return raws


def rank(query: Query) -> list[dict]:
    """
    Fetch from DICE and RA live, filter by neighbourhood, sort by date.
    Returns list of dicts ready for list_view rendering.
    """
    raws: list[RawEvent] = asyncio.run(_fetch_all(query))

    # Persist to KB for card/detail access later
    if raws:
        ingest(raws)

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
    }
