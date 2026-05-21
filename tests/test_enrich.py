import json
import pytest
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from pathlib import Path


def mock_claude_response(payload: dict):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(payload))]
    mock_msg.usage = MagicMock(input_tokens=100, output_tokens=50)
    return mock_msg


@pytest.fixture(autouse=True)
def patch_token_ledger(monkeypatch):
    monkeypatch.setattr("whereabout.query.enrich.check_and_record", lambda i, o: None)


def test_artist_bio_cached_7d(tmp_path, monkeypatch):
    """Artist bio cached in DB is returned without calling Claude again."""
    import whereabout.db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "test.db")

    from whereabout.query.enrich import enrich_artist

    # lookup_artist returns nothing so Claude is used
    bio_payload = {"bio": "Test artist biography.", "genres": ["jazz"], "notable_for": "Known for test"}
    with patch("whereabout.query.enrich.lookup_artist", return_value=None), \
         patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_claude_response(bio_payload)
        result1 = enrich_artist("Test Artist")

    assert result1["bio"] == "Test artist biography."
    assert result1["cached"] is False

    # Second call within 7 days: returned from DB cache, no network call
    with patch("whereabout.query.enrich.lookup_artist", return_value=None), \
         patch("anthropic.Anthropic") as mock_client:
        result2 = enrich_artist("Test Artist")
        mock_client.return_value.messages.create.assert_not_called()

    assert result2["bio"] == "Test artist biography."
    assert result2["cached"] is True


def test_token_budget_refuses_when_daily_exhausted(tmp_path, monkeypatch):
    """BudgetExceeded is raised when daily token cap is exhausted."""
    import whereabout.token_ledger as tl
    monkeypatch.setattr(tl, "LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr("whereabout.query.enrich.check_and_record", tl.check_and_record)

    from whereabout.token_ledger import BudgetExceeded, DAILY_CAP, _save
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _save({today: {"input_tokens": DAILY_CAP, "output_tokens": 0}})

    import whereabout.db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "test.db")

    from whereabout.query.enrich import enrich_artist
    with patch("whereabout.query.enrich.lookup_artist", return_value=None), \
         patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_claude_response(
            {"bio": "x", "genres": [], "notable_for": ""}
        )
        with pytest.raises(BudgetExceeded):
            enrich_artist("Unknown Artist")
