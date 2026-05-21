from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from whereabout.models import Query
from whereabout.config import UserConfig
from whereabout import neighbourhoods as nb
from whereabout.claude_cli import call_claude


_PROMPT_PATH = Path(__file__).parent.parent.parent / "claude-skill" / "prompts" / "parse_query.md"
_FALLBACK_PROMPT = '{"genres": [], "neighbourhood": null, "date_range_days": 14, "did_you_mean": null}'


def _load_prompt_template() -> str:
    return _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else _FALLBACK_PROMPT


def parse(raw_text: str) -> Query:
    """Parse a natural-language query into a structured Query using Claude."""
    cfg = UserConfig.load()
    neighbourhood_enum = "\n".join(f"- {n}" for n in sorted(nb.list_all()))
    template = _load_prompt_template()
    system_prompt = template.replace("{{NEIGHBOURHOOD_ENUM}}", neighbourhood_enum)

    raw_json = call_claude(raw_text, system_prompt=system_prompt)
    # Strip markdown fences if present
    if raw_json.startswith("```"):
        raw_json = raw_json.split("```")[1]
        if raw_json.startswith("json"):
            raw_json = raw_json[4:]
    parsed = json.loads(raw_json.strip())

    genres = [g.lower().strip() for g in parsed.get("genres", [])]
    neighbourhood_name = parsed.get("neighbourhood")
    did_you_mean_val = parsed.get("did_you_mean")
    date_range_days = int(parsed.get("date_range_days", 14))

    # Resolve home neighbourhood if none specified
    if neighbourhood_name is None and not raw_text_mentions_location(raw_text):
        if cfg.home_neighbourhood:
            neighbourhood_name = cfg.home_neighbourhood

    # Return did-you-mean info via Query raw_text field for CLI to surface
    effective_text = raw_text
    if did_you_mean_val and neighbourhood_name is None:
        effective_text = f"{raw_text} [did_you_mean:{did_you_mean_val}]"

    now = datetime.now(timezone.utc)
    return Query(
        raw_text=effective_text,
        genres=genres,
        neighbourhood=neighbourhood_name,
        date_range_start_utc=now,
        date_range_end_utc=now + timedelta(days=date_range_days),
    )


def raw_text_mentions_location(text: str) -> bool:
    """True if the query contains an explicit location mention (not 'around me' / 'near me')."""
    lower = text.lower()
    # "around me" and "near me" are NOT explicit locations — they mean "use my home"
    vague_phrases = ["around me", "near me"]
    if any(p in lower for p in vague_phrases):
        return False
    location_words = ["in ", "near ", "around ", "at "]
    return any(w in lower for w in location_words)
