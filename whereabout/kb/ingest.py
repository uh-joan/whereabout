from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from importlib.resources import files

from whereabout.models import RawEvent
from whereabout.db import get_connection
from whereabout import neighbourhoods as nb

# Build reverse genre-alias map once at import time
def _build_reverse_alias_map() -> dict[str, str]:
    try:
        raw = files("whereabout.data").joinpath("genre_aliases.json").read_text()
        aliases: dict[str, list[str]] = json.loads(raw)
        return {alias.lower(): canonical for canonical, lst in aliases.items() for alias in lst}
    except Exception:
        return {}

_GENRE_REVERSE: dict[str, str] = _build_reverse_alias_map()


def stable_hash(raw: RawEvent) -> str:
    venue_pc = (raw.venue_postcode or "").upper().replace(" ", "")
    date_min = raw.date_start_utc.strftime("%Y%m%dT%H%M")
    first_artist = (
        raw.artists[0].lower().strip() if raw.artists else raw.title.lower().strip()
    )
    # Fall back to source|source_event_id when EITHER signal is missing
    if not first_artist or not venue_pc:
        key = f"{raw.source}|{raw.source_event_id}"
    else:
        key = f"{venue_pc}|{date_min}|{first_artist}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def ingest(raws: list[RawEvent]) -> int:
    """Normalise and upsert RawEvents into SQLite. Returns count of rows upserted."""
    if not raws:
        return 0
    upserted = 0
    with get_connection() as conn:
        for raw in raws:
            neighbourhood_id = None
            if raw.venue_postcode:
                name = nb.resolve_postcode_prefix(raw.venue_postcode)
                if name:
                    row = conn.execute(
                        "SELECT id FROM neighbourhoods WHERE name = ?", (name,)
                    ).fetchone()
                    if row:
                        neighbourhood_id = row[0]

            venue_id = _upsert_venue(conn, raw, neighbourhood_id)
            artist_ids = [_upsert_artist(conn, name) for name in raw.artists]
            genres = _normalise_genres(raw.genres_raw)
            sh = stable_hash(raw)

            existing = conn.execute(
                "SELECT id, sources, source_urls FROM events WHERE stable_hash = ?",
                (sh,),
            ).fetchone()

            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            if existing:
                # Merge sources
                sources = list(set(json.loads(existing["sources"]) + [raw.source]))
                source_urls = list(
                    set(json.loads(existing["source_urls"]) + [raw.source_url])
                )
                conn.execute(
                    "UPDATE events SET sources=?, source_urls=?, scraped_at_utc=? WHERE id=?",
                    (
                        json.dumps(sources),
                        json.dumps(source_urls),
                        now_utc,
                        existing["id"],
                    ),
                )
                event_id = existing["id"]
            else:
                cur = conn.execute(
                    """INSERT INTO events
                       (stable_hash, title, date_start_utc, genres, venue_id, ticket_url,
                        sources, source_urls, scraped_at_utc, raw_payload)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        sh,
                        raw.title,
                        raw.date_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        json.dumps(genres),
                        venue_id,
                        raw.ticket_url,
                        json.dumps([raw.source]),
                        json.dumps([raw.source_url]),
                        now_utc,
                        json.dumps(raw.raw_payload),
                    ),
                )
                event_id = cur.lastrowid
                upserted += 1

            for artist_id in artist_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO event_artists(event_id, artist_id) VALUES (?,?)",
                    (event_id, artist_id),
                )

        conn.commit()
    return upserted


def _upsert_venue(conn, raw: RawEvent, neighbourhood_id: int | None) -> int:
    postcode = (raw.venue_postcode or "").upper().strip() or None
    # postcode_normalised is a generated column: UPPER(REPLACE(postcode, ' ', ''))
    normalised = (postcode or "").replace(" ", "")
    row = conn.execute(
        "SELECT id FROM venues WHERE LOWER(name) = LOWER(?) AND postcode_normalised = ?",
        (raw.venue_name, normalised),
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        """INSERT INTO venues(name, address, postcode, neighbourhood_id, lat, lng)
           VALUES (?,?,?,?,?,?)""",
        (
            raw.venue_name,
            raw.venue_address,
            postcode,
            neighbourhood_id,
            raw.venue_lat,
            raw.venue_lng,
        ),
    )
    return cur.lastrowid


def _upsert_artist(conn, name: str) -> int:
    row = conn.execute("SELECT id FROM artists WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO artists(name, genres) VALUES (?, '[]')", (name,))
    return cur.lastrowid


def _normalise_genres(raw_genres: list[str]) -> list[str]:
    normalised = []
    for g in raw_genres:
        g_lower = g.lower().strip()
        # Strip DICE namespace prefix (e.g. "gig:jazz" → "jazz", "dj:soul" → "soul")
        g_bare = g_lower.split(":")[-1] if ":" in g_lower else g_lower
        normalised.append(_GENRE_REVERSE.get(g_bare, g_bare))
    return list(dict.fromkeys(normalised))
