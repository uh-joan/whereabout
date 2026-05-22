from __future__ import annotations
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

_HISTORY_PATH = Path.home() / ".cache" / "whereabout" / "session_history"
_BANNER = """\
whereabout — hyper-local live music discovery
Type a search query, a result number to get details, or 'quit' to exit.
"""


def run_session(home_neighbourhood: str | None = None) -> None:
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    session: PromptSession = PromptSession(
        history=FileHistory(str(_HISTORY_PATH)),
        auto_suggest=AutoSuggestFromHistory(),
    )

    print(_BANNER)

    last_results: list[dict] = []

    while True:
        try:
            text = session.prompt("▶ ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        # Number → drill into last results
        if text.isdigit():
            idx = int(text) - 1
            if not last_results:
                print("No results yet — run a search first.")
                continue
            if idx < 0 or idx >= len(last_results):
                print(f"Enter a number between 1 and {len(last_results)}.")
                continue
            _show_detail(last_results[idx])
            continue

        # Otherwise treat as a search query
        last_results = _run_query(text, home_neighbourhood)


def _run_query(text: str, home_neighbourhood: str | None) -> list[dict]:
    from whereabout.query import parser, ranker
    from whereabout.output import list_view
    from whereabout.config import UserConfig
    import re

    cfg = UserConfig.load()
    try:
        q = parser.parse(text)
    except Exception as e:
        print(f"Parser error: {e}")
        return []

    if "[did_you_mean:" in q.raw_text:
        m = re.search(r"\[did_you_mean:(.+?)\]", q.raw_text)
        if m:
            print(f"No exact match — showing results for {m.group(1)}.")

    effective_neighbourhood = q.neighbourhood or cfg.home_neighbourhood
    if effective_neighbourhood:
        q = q.model_copy(update={"neighbourhood": effective_neighbourhood})

    try:
        results = ranker.rank(q)
    except Exception as e:
        print(f"Fetch error: {e}")
        return []

    neighbourhood_label = effective_neighbourhood or "London"
    genre_label = "/".join(q.genres) if q.genres else "all genres"
    delta_days = max(1, (q.date_range_end_utc - q.date_range_start_utc).days)
    if delta_days == 1:
        date_label = "tonight"
    elif delta_days == 2:
        date_label = "tomorrow"
    elif delta_days <= 4:
        date_label = "this weekend"
    elif delta_days <= 7:
        date_label = "this week"
    else:
        date_label = f"next {delta_days} days"
    query_label = f"{genre_label} in {neighbourhood_label} — {date_label}"

    sources = sorted({r["source"] for r in results}) if results else []
    source_note = "live (" + " + ".join(s.replace("_", " ").upper() for s in sources) + ")" if sources else "live"
    print(list_view.render_markdown(results, query_label, source_note))
    return results


def _show_detail(result: dict) -> None:
    import json
    from zoneinfo import ZoneInfo
    from datetime import datetime, timezone
    from whereabout.db import get_connection
    from whereabout.output import detail_view
    from whereabout.query.enrich import enrich_artist

    stable_hash = result.get("stable_hash", "")
    if not stable_hash:
        print("No ID for this result.")
        return

    with get_connection() as conn:
        row = conn.execute(
            """SELECT e.*, v.name as venue_name, v.postcode as venue_postcode
               FROM events e LEFT JOIN venues v ON e.venue_id = v.id
               WHERE e.stable_hash LIKE ?
               LIMIT 1""",
            (f"%{stable_hash}%",)
        ).fetchone()

        if not row:
            print("Event not found in KB — try running a new search to refresh.")
            return

        artist_rows = conn.execute(
            """SELECT a.name FROM artists a
               JOIN event_artists ea ON a.id = ea.artist_id
               WHERE ea.event_id = ?""",
            (row["id"],)
        ).fetchall()

    dt = datetime.fromisoformat(row["date_start_utc"].replace("Z", "+00:00"))
    local_dt = dt.astimezone(ZoneInfo("Europe/London"))
    artists = [r["name"] for r in artist_rows]
    event_genres = json.loads(row["genres"])

    detail = {
        "title": row["title"],
        "artists": artists,
        "venue": row["venue_name"] or "",
        "postcode": row["venue_postcode"] or "",
        "date_local": local_dt.strftime("%a %d %b"),
        "time_local": local_dt.strftime("%H:%M"),
        "ticket_url": row["ticket_url"],
        "price": "",
        "genres": event_genres,
    }

    enrichments = {}
    for artist in artists:
        try:
            enrichments[artist] = enrich_artist(artist, context_genres=event_genres)
        except Exception as e:
            enrichments[artist] = {"bio": f"(enrichment unavailable: {e})", "genres": [], "notable_for": ""}

    print(detail_view.render_markdown(detail, enrichments))
