"""Postcode-prefix based neighbourhood resolver for London."""
from __future__ import annotations
import json
from importlib.resources import files
from difflib import get_close_matches


def _load_neighbourhoods() -> list[dict]:
    data = files("whereabout.data").joinpath("neighbourhoods.json").read_text()
    return json.loads(data)


_NEIGHBOURHOODS = _load_neighbourhoods()

# Build prefix → name lookup
_PREFIX_MAP: dict[str, str] = {}
for _n in _NEIGHBOURHOODS:
    for _p in _n["postcode_prefixes"]:
        _PREFIX_MAP[_p.upper()] = _n["name"]

# Build canonical name set
_KNOWN_NAMES: set[str] = {n["name"].lower() for n in _NEIGHBOURHOODS}
_ALL_NAMES: list[str] = [n["name"] for n in _NEIGHBOURHOODS]


def resolve_postcode_prefix(postcode: str) -> str | None:
    """Return canonical neighbourhood name for a postcode, or None."""
    if not postcode:
        return None
    # Match only the full outward code (part before the space).
    # "SE1 3HB" → "SE1", "EC2A 4AB" → "EC2A", "E10 7JQ" → "E10".
    # All entries in _PREFIX_MAP are full outward codes, so substring
    # matching is unnecessary and causes cross-district false positives.
    outward = postcode.strip().upper().split()[0]
    return _PREFIX_MAP.get(outward)


def resolve_name(name: str) -> str | None:
    """Return canonical neighbourhood name for a user-supplied name, or None."""
    if not name:
        return None
    lower = name.lower().strip()
    # Exact match on canonical name
    for n in _NEIGHBOURHOODS:
        if n["name"].lower() == lower:
            return n["name"]
        # Match aliases
        if lower in [a.lower() for a in n.get("aliases", [])]:
            return n["name"]
        # Match ward_aliases
        if lower in [w.lower() for w in n.get("ward_aliases", [])]:
            return n["name"]
    return None


def did_you_mean(name: str, n: int = 3) -> list[str]:
    """Return up to n closest canonical neighbourhood names."""
    matches = get_close_matches(name.lower(), [x.lower() for x in _ALL_NAMES], n=n, cutoff=0.4)
    # Map back to canonical names preserving case
    lower_to_canonical = {x.lower(): x for x in _ALL_NAMES}
    return [lower_to_canonical[m] for m in matches]


def list_all() -> list[str]:
    return list(_ALL_NAMES)


def nearby_neighbourhoods(name: str, max_count: int = 4) -> list[str]:
    """Return up to max_count nearest neighbourhood names by centroid distance."""
    import math
    target = next((n for n in _NEIGHBOURHOODS if n["name"] == name), None)
    if not target:
        return []
    distances = []
    for n in _NEIGHBOURHOODS:
        if n["name"] == name or not n.get("postcode_prefixes"):
            continue
        d = math.sqrt((n["lat"] - target["lat"]) ** 2 + (n["lng"] - target["lng"]) ** 2)
        distances.append((d, n["name"]))
    distances.sort()
    return [name for _, name in distances[:max_count]]
