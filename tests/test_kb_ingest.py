import json
import pytest
from datetime import datetime, timezone
from whereabout.kb.ingest import ingest, stable_hash
from whereabout.models import RawEvent


def make_raw(source="dice_fm", event_id="evt-1", postcode="SW2 1DF",
             artist="Test Artist", title="Test Gig", date_str="2026-06-06T20:00:00Z") -> RawEvent:
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
    return RawEvent(
        source=source,
        source_event_id=event_id,
        source_url=f"https://dice.fm/event/{event_id}",
        title=title,
        date_start_utc=dt,
        venue_name="Test Venue",
        venue_address="1 Test St, London",
        venue_postcode=postcode,
        artists=[artist],
        genres_raw=["jazz"],
        raw_payload={},
    )


def test_idempotent_upsert(tmp_path, monkeypatch):
    """Running ingest twice with the same event produces same row count."""
    import whereabout.db as db_mod
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)

    raw = make_raw()
    count1 = ingest([raw])
    assert count1 == 1

    count2 = ingest([raw])
    assert count2 == 0  # already exists, upserted (not newly inserted)

    # Verify only 1 row exists
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()
    assert total == 1


def test_multi_source_dedupe(tmp_path, monkeypatch):
    """Same gig from two sources collapses to one row; sources array has both."""
    import whereabout.db as db_mod
    db_path = tmp_path / "test2.db"
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)

    raw_dice = make_raw(source="dice_fm", event_id="dice-001")
    raw_ra = make_raw(source="resident_advisor", event_id="ra-001")
    # Same artist+postcode+date = same stable_hash

    ingest([raw_dice])
    ingest([raw_ra])

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT stable_hash, sources FROM events").fetchall()
    conn.close()

    assert len(rows) == 1
    sources = json.loads(rows[0][1])
    assert "dice_fm" in sources
    assert "resident_advisor" in sources
