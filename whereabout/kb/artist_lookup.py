from __future__ import annotations
import json
import os
import re
import difflib
from pathlib import Path
import httpx

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

# Last.fm public API key — register your own at https://www.last.fm/api/account/create
_LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY", "b25b959554ed76058ac220b7b2e0a026")
_LASTFM_URL = "http://ws.audioscrobbler.com/2.0/"

_RA_GRAPHQL_URL = "https://ra.co/graphql"
_RA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Referer": "https://ra.co/",
    "Origin": "https://ra.co",
}

_RA_SEARCH_QUERY = """
query ArtistSearch($term: String!) {
  search(searchTerm: $term, limit: 3, indices: [ARTIST]) {
    id value searchType
  }
}
"""

_RA_ARTIST_QUERY = """
query GetArtist($id: ID!) {
  artist(id: $id) {
    name
    biography { content }
    soundcloud bandcamp website
  }
}
"""

# Strip Last.fm trailing "Read more on Last.fm" link
_LASTFM_LINK_RE = re.compile(r'<a\s[^>]*href="https://www\.last\.fm[^"]*"[^>]*>.*?</a>', re.IGNORECASE)
# Strip country/region suffixes and punctuation for name comparison
_NAME_NORM_RE = re.compile(r'[\s\(\)\.\?\:\-]+')
_COUNTRY_SUFFIX_RE = re.compile(r'\b(uk|us|usa|de|fr|nl|au|ca)\b', re.IGNORECASE)
_MIN_LISTENERS = 500
_MIN_NAME_RATIO = 0.6


def _normalize_name(name: str) -> str:
    s = _COUNTRY_SUFFIX_RE.sub("", name.lower())
    return _NAME_NORM_RE.sub("", s)


def lookup_artist(name: str, context_genres: list[str] | None = None) -> dict | None:
    """
    Try Last.fm then RA for structured artist data.
    context_genres: event genres used to validate Last.fm matches (e.g. ["techno", "house"]).
    Returns {"bio": str, "genres": list[str], "links": dict} or None if not found.
    """
    result = _lookup_lastfm(name, context_genres or [])
    if result:
        return result
    return _lookup_ra(name)


def _lookup_lastfm(name: str, context_genres: list[str]) -> dict | None:
    try:
        r = httpx.get(
            _LASTFM_URL,
            params={"method": "artist.getinfo", "artist": name, "api_key": _LASTFM_API_KEY, "format": "json"},
            timeout=8,
        )
        data = r.json()
    except Exception:
        return None

    if "error" in data or "artist" not in data:
        return None

    artist = data["artist"]
    returned_name = artist.get("name", "")
    listeners = int((artist.get("stats") or {}).get("listeners", 0))
    tags = [t["name"] for t in (artist.get("tags") or {}).get("tag", [])]

    # Reject stubs: very few listeners and no genre tags
    if listeners < _MIN_LISTENERS and not tags:
        return None

    # Reject if returned name diverges significantly from what we searched
    ratio = difflib.SequenceMatcher(None, _normalize_name(name), _normalize_name(returned_name)).ratio()
    if ratio < _MIN_NAME_RATIO:
        return None

    # Reject if Last.fm tags are incompatible with the event's genre context
    if context_genres and tags:
        context_expanded = _expand_genres(context_genres)
        lastfm_normalized = {t.lower() for t in tags}
        if not context_expanded & lastfm_normalized:
            return None

    bio_raw = (artist.get("bio") or {}).get("summary", "").strip()
    bio = _LASTFM_LINK_RE.sub("", bio_raw).strip()
    if not bio:
        return None

    return {"bio": bio, "genres": tags}


def _lookup_ra(name: str) -> dict | None:
    try:
        # Step 1: search for artist by name
        r = httpx.post(
            _RA_GRAPHQL_URL,
            json={"query": _RA_SEARCH_QUERY, "variables": {"term": name}},
            headers=_RA_HEADERS,
            timeout=10,
        )
        results = (r.json().get("data") or {}).get("search") or []
    except Exception:
        return None

    # Find first ARTIST result with a name close enough to what we searched
    artist_id = None
    for result in results:
        if result.get("searchType") == "ARTIST":
            artist_id = result["id"]
            break

    if not artist_id:
        return None

    try:
        # Step 2: fetch full artist profile
        r2 = httpx.post(
            _RA_GRAPHQL_URL,
            json={"query": _RA_ARTIST_QUERY, "variables": {"id": artist_id}},
            headers=_RA_HEADERS,
            timeout=10,
        )
        artist = (r2.json().get("data") or {}).get("artist") or {}
    except Exception:
        return None

    bio = ((artist.get("biography") or {}).get("content") or "").strip()
    links = {k: artist[k] for k in ("soundcloud", "bandcamp", "website") if artist.get(k)}

    if not bio and not links:
        return None

    return {"bio": bio, "genres": [], "links": links}
