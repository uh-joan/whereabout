from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from whereabout.claude_cli import call_claude
from whereabout.db import get_connection
from whereabout.kb.artist_lookup import lookup_artist


_PROMPT_PATH = Path(__file__).parent.parent.parent / "claude-skill" / "prompts" / "enrich_artist.md"
_CACHE_TTL_DAYS = 7


def _load_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text()
    return 'Return JSON: {"bio": "No information available.", "genres": [], "notable_for": ""}'


def enrich_artist(artist_name: str, context_genres: list[str] | None = None) -> dict:
    """
    Fetch artist bio, cached 7 days. Tries Last.fm → RA → Claude.
    context_genres: event genres used to validate Last.fm matches.
    """
    # Check DB cache first
    with get_connection() as conn:
        row = conn.execute(
            "SELECT bio, genres, last_enriched_at FROM artists WHERE LOWER(name) = LOWER(?)",
            (artist_name,)
        ).fetchone()

    if row and row["last_enriched_at"]:
        enriched_at = datetime.fromisoformat(row["last_enriched_at"].replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - enriched_at
        if age < timedelta(days=_CACHE_TTL_DAYS) and row["bio"]:
            return {
                "bio": row["bio"],
                "genres": json.loads(row["genres"] or "[]"),
                "notable_for": "",
                "cached": True,
            }

    # Try structured sources first (Last.fm → RA), fall back to Claude
    looked_up = lookup_artist(artist_name, context_genres or [])
    if looked_up:
        data = {
            "bio": looked_up["bio"],
            "genres": looked_up.get("genres", []),
            "notable_for": "",
            "links": looked_up.get("links", {}),
        }
    else:
        system_prompt = _load_prompt()
        raw = call_claude(f"Artist: {artist_name}", system_prompt=system_prompt)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"bio": raw[:200], "genres": [], "notable_for": ""}

    # Cache in DB
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO artists(name, bio, genres, last_enriched_at)
               VALUES (?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                 bio=excluded.bio,
                 genres=excluded.genres,
                 last_enriched_at=excluded.last_enriched_at""",
            (artist_name, data.get("bio", ""), json.dumps(data.get("genres", [])), now_utc)
        )
        conn.commit()

    return {**data, "cached": False}
