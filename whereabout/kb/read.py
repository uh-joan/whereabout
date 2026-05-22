from __future__ import annotations
import json
from datetime import datetime, timezone
from whereabout.models import RawEvent
from whereabout.db import get_connection


def read_events_for_range(date_start_utc: datetime, date_end_utc: datetime) -> list[RawEvent]:
    """Read events from KB in the given UTC date range as RawEvent objects."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT e.id, e.sources, e.source_urls,
                      e.title, e.date_start_utc, e.genres, e.ticket_url,
                      v.name as venue_name, v.postcode as venue_postcode
               FROM events e
               LEFT JOIN venues v ON e.venue_id = v.id
               WHERE e.date_start_utc >= ? AND e.date_start_utc <= ?""",
            (date_start_utc.isoformat(), date_end_utc.isoformat()),
        ).fetchall()

        result = []
        for row in rows:
            artist_rows = conn.execute(
                """SELECT a.name FROM artists a
                   JOIN event_artists ea ON a.id = ea.artist_id
                   WHERE ea.event_id = ?""",
                (row["id"],),
            ).fetchall()

            dt_str = row["date_start_utc"].replace("Z", "+00:00")
            dt = datetime.fromisoformat(dt_str)
            genres = json.loads(row["genres"] or "[]")

            sources = json.loads(row["sources"] or "[]")
            source = sources[0] if sources else ""

            source_urls = json.loads(row["source_urls"] or "[]")
            source_url = source_urls[0] if source_urls else ""

            result.append(RawEvent(
                source=source,
                source_event_id="",
                source_url=source_url,
                title=row["title"] or "",
                date_start_utc=dt,
                venue_name=row["venue_name"] or "",
                venue_postcode=row["venue_postcode"] or "",
                artists=[r["name"] for r in artist_rows],
                genres_raw=genres,
                ticket_url=row["ticket_url"],
                price_text=None,
                raw_payload={},
            ))
        return result
