import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from whereabout.query.parser import parse
from whereabout.config import UserConfig, CONFIG_PATH


def mock_claude_response(json_payload: dict):
    """Create a mock Anthropic message response."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(json_payload))]
    mock_message.usage = MagicMock(input_tokens=100, output_tokens=50)
    return mock_message


@pytest.fixture(autouse=True)
def mock_token_ledger(monkeypatch):
    """Don't write token ledger during tests."""
    monkeypatch.setattr("whereabout.query.parser.check_and_record", lambda i, o: None)


def test_around_me_uses_config(tmp_path, monkeypatch):
    """'around me' with no explicit location resolves to home neighbourhood from config."""
    # Set home neighbourhood
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "config.toml")
    cfg = UserConfig(home_neighbourhood="Camden")
    cfg.save()

    response = {"genres": ["jazz"], "neighbourhood": None, "date_range_days": 14, "did_you_mean": None}
    with patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_claude_response(response)
        monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "config.toml")
        q = parse("show me jazz gigs around me")

    assert q.neighbourhood == "Camden"
    assert "jazz" in q.genres


def test_explicit_overrides_home(tmp_path, monkeypatch):
    """Explicit location in query overrides home neighbourhood."""
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "config.toml")
    cfg = UserConfig(home_neighbourhood="Camden")
    cfg.save()

    response = {"genres": ["soul"], "neighbourhood": "Brixton", "date_range_days": 3, "did_you_mean": None}
    with patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_claude_response(response)
        q = parse("soul music in brixton this weekend")

    assert q.neighbourhood == "Brixton"


def test_genre_aliases(tmp_path, monkeypatch):
    """neo-soul in query normalises to soul in genres."""
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "config.toml")
    response = {"genres": ["soul"], "neighbourhood": "Dalston", "date_range_days": 14, "did_you_mean": None}
    with patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_claude_response(response)
        q = parse("neo-soul in hackney")

    assert "soul" in q.genres


def test_unknown_neighbourhood_returns_did_you_mean(tmp_path, monkeypatch):
    """Unknown neighbourhood triggers did-you-mean in raw_text."""
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "config.toml")
    response = {"genres": ["jazz"], "neighbourhood": None, "date_range_days": 14, "did_you_mean": "Crystal Palace"}
    with patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_claude_response(response)
        q = parse("jazz in croydon")

    assert "did_you_mean:Crystal Palace" in q.raw_text
