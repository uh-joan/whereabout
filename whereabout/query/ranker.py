from __future__ import annotations
import asyncio
from whereabout.models import Query, RawEvent, Event, Venue, Artist
from whereabout.sources.dice_fm import DICESource
from whereabout import neighbourhoods as nb
from whereabout.kb.ingest import ingest


def rank(query: Query) -> list[dict]:
    """
    Fetch from DICE live, filter by neighbourhood, sort by date.
    Returns list of dicts ready for list_view rendering.
    """
    source = DICESource()
    raws: list[RawEvent] = asyncio.run(source.fetch(query))

    # Persist to KB for card/detail access later
    if raws:
        ingest(raws)

    # Filter by neighbourhood if specified
    if query.neighbourhood:
        raws = _filter_by_neighbourhood(raws, query.neighbourhood)

    # Filter by genre if specified
    if query.genres:
        raws = _filter_by_genre(raws, query.genres)

    # Filter to date range
    raws = [r for r in raws
            if query.date_range_start_utc <= r.date_start_utc <= query.date_range_end_utc]

    # Sort by date ascending
    raws.sort(key=lambda r: r.date_start_utc)

    return [_to_result_dict(r, i + 1) for i, r in enumerate(raws[:query.limit])]


def _filter_by_neighbourhood(raws: list[RawEvent], neighbourhood: str) -> list[RawEvent]:
    result = []
    for raw in raws:
        if raw.venue_postcode:
            resolved = nb.resolve_postcode_prefix(raw.venue_postcode)
            if resolved and resolved.lower() == neighbourhood.lower():
                result.append(raw)
    return result


def _filter_by_genre(raws: list[RawEvent], genres: list[str]) -> list[RawEvent]:
    genre_set = {g.lower() for g in genres}
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
    }
