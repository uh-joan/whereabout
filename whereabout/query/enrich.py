from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic

from whereabout.token_ledger import check_and_record
from whereabout.db import get_connection


_PROMPT_PATH = Path(__file__).parent.parent.parent / "claude-skill" / "prompts" / "enrich_artist.md"
_CACHE_TTL_DAYS = 30


def _load_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text()
    return 'Return JSON: {"bio": "No information available.", "genres": [], "notable_for": ""}'


def enrich_artist(artist_name: str) -> dict:
    """
    Fetch artist bio via Claude, cached 30 days in artists table.
    Returns dict with bio, genres, notable_for.
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

    # Fetch from Claude
    system_prompt = _load_prompt()
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=256,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Artist: {artist_name}"}],
    )
    check_and_record(message.usage.input_tokens, message.usage.output_tokens)

    raw = message.content[0].text.strip()
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
