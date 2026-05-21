from __future__ import annotations
import os
import sqlite3
from pathlib import Path

from whereabout.config import CONFIG_PATH
from whereabout.db import DB_PATH
from whereabout.token_ledger import get_today_usage


def run_checks() -> list[tuple[bool, str]]:
    """Return list of (passed, message) for each check."""
    results = []

    # 1. config
    try:
        if CONFIG_PATH.exists():
            import tomllib
            with open(CONFIG_PATH, "rb") as f:
                tomllib.load(f)
            results.append((True, "✓ config"))
        else:
            results.append((False, "✗ config  — not found; run: whereabout config init"))
    except Exception as e:
        results.append((False, f"✗ config  — parse error: {e}"))

    # 2. db
    try:
        if DB_PATH.exists():
            conn = sqlite3.connect(str(DB_PATH))
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            conn.close()
            required = {"neighbourhoods", "venues", "artists", "events"}
            missing = required - tables
            if missing:
                results.append((False, f"✗ db      — missing tables: {missing}"))
            else:
                results.append((True, "✓ db"))
        else:
            results.append((False, f"✗ db      — not found at {DB_PATH}; run whereabout once to initialise"))
    except Exception as e:
        results.append((False, f"✗ db      — error: {e}"))

    # 3. playwright (deferred to v1.1; always passes in v1.0)
    results.append((True, "✓ playwright  (v1.1 — not required in v1.0)"))

    # 4. kb_meta
    try:
        if DB_PATH.exists():
            conn = sqlite3.connect(str(DB_PATH))
            row = conn.execute("SELECT source, last_refreshed_at FROM kb_meta LIMIT 1").fetchone()
            conn.close()
            if row:
                results.append((True, f"✓ kb_meta     last refresh: {row[0]} {row[1]}"))
            else:
                results.append((True, "✓ kb_meta     (live DICE — no scheduled refresh in v1.0)"))
        else:
            results.append((False, "✗ kb_meta — db not initialised"))
    except Exception as e:
        results.append((False, f"✗ kb_meta — error: {e}"))

    # 5. api_key
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key and key.startswith("sk-ant-"):
        results.append((True, "✓ api_key"))
    elif key:
        results.append((True, "✓ api_key  (set, format unverified)"))
    else:
        results.append((False, "✗ api_key — ANTHROPIC_API_KEY not set"))

    return results
