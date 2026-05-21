import json
import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta


def test_artist_bio_cached_7d(tmp_path, monkeypatch):
    """Artist bio cached in DB is returned without calling claude CLI again."""
    import whereabout.db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "test.db")

    from whereabout.query.enrich import enrich_artist

    bio_payload = {"bio": "Test artist biography.", "genres": ["jazz"], "notable_for": "Known for test"}
    with patch("whereabout.query.enrich.lookup_artist", return_value=None), \
         patch("whereabout.query.enrich.call_claude", return_value=json.dumps(bio_payload)):
        result1 = enrich_artist("Test Artist")

    assert result1["bio"] == "Test artist biography."
    assert result1["cached"] is False

    # Second call within 7 days: returned from DB cache, no CLI call
    with patch("whereabout.query.enrich.lookup_artist", return_value=None), \
         patch("whereabout.query.enrich.call_claude", side_effect=AssertionError("should not call CLI")):
        result2 = enrich_artist("Test Artist")

    assert result2["bio"] == "Test artist biography."
    assert result2["cached"] is True
