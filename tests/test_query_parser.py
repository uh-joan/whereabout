import pytest
import json
from unittest.mock import patch
from whereabout.query.parser import parse
from whereabout.config import UserConfig


def test_around_me_uses_config(tmp_path, monkeypatch):
    """'around me' with no explicit location resolves to home neighbourhood from config."""
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "config.toml")
    cfg = UserConfig(home_neighbourhood="Camden")
    cfg.save()

    response = {"genres": ["jazz"], "neighbourhood": None, "date_range_days": 14, "did_you_mean": None}
    with patch("whereabout.query.parser.call_claude", return_value=json.dumps(response)):
        q = parse("show me jazz gigs around me")

    assert q.neighbourhood == "Camden"
    assert "jazz" in q.genres


def test_explicit_overrides_home(tmp_path, monkeypatch):
    """Explicit location in query overrides home neighbourhood."""
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "config.toml")
    cfg = UserConfig(home_neighbourhood="Camden")
    cfg.save()

    response = {"genres": ["soul"], "neighbourhood": "Brixton", "date_range_days": 3, "did_you_mean": None}
    with patch("whereabout.query.parser.call_claude", return_value=json.dumps(response)):
        q = parse("soul music in brixton this weekend")

    assert q.neighbourhood == "Brixton"


def test_genre_aliases(tmp_path, monkeypatch):
    """neo-soul in query normalises to soul in genres."""
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "config.toml")
    response = {"genres": ["soul"], "neighbourhood": "Dalston", "date_range_days": 14, "did_you_mean": None}
    with patch("whereabout.query.parser.call_claude", return_value=json.dumps(response)):
        q = parse("neo-soul in hackney")

    assert "soul" in q.genres


def test_unknown_neighbourhood_returns_did_you_mean(tmp_path, monkeypatch):
    """Unknown neighbourhood triggers did-you-mean in raw_text."""
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "config.toml")
    response = {"genres": ["jazz"], "neighbourhood": None, "date_range_days": 14, "did_you_mean": "Crystal Palace"}
    with patch("whereabout.query.parser.call_claude", return_value=json.dumps(response)):
        q = parse("jazz in croydon")

    assert "did_you_mean:Crystal Palace" in q.raw_text
