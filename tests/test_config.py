import pytest
from pathlib import Path
from unittest.mock import patch
from whereabout.config import UserConfig, CONFIG_PATH


def test_default_config():
    cfg = UserConfig()
    assert cfg.home_neighbourhood == ""
    assert cfg.default_horizon_days == 14
    assert cfg.default_result_limit == 10
    assert cfg.preferred_genres == []


def test_is_first_run_no_file():
    with patch.object(Path, "exists", return_value=False):
        cfg = UserConfig()
        assert cfg.is_first_run() is True


def test_is_first_run_empty_neighbourhood():
    cfg = UserConfig(home_neighbourhood="")
    # is_first_run checks both file existence and home_neighbourhood
    assert cfg.is_first_run() is True


def test_is_first_run_with_neighbourhood(tmp_path, monkeypatch):
    # Point CONFIG_PATH to a temp file that exists
    tmp_config = tmp_path / "config.toml"
    tmp_config.write_bytes(b'home_neighbourhood = "Brixton"\ndefault_horizon_days = 14\ndefault_result_limit = 10\npreferred_genres = []\n')
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_config)
    cfg = UserConfig.load()
    assert cfg.home_neighbourhood == "Brixton"
    assert cfg.is_first_run() is False


def test_save_and_load(tmp_path, monkeypatch):
    tmp_config = tmp_path / "config.toml"
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_config)
    cfg = UserConfig(
        home_neighbourhood="Camden",
        default_horizon_days=7,
        default_result_limit=5,
        preferred_genres=["jazz", "soul"],
    )
    cfg.save()
    assert tmp_config.exists()
    loaded = UserConfig.load()
    assert loaded.home_neighbourhood == "Camden"
    assert loaded.default_horizon_days == 7
    assert loaded.default_result_limit == 5
    assert loaded.preferred_genres == ["jazz", "soul"]


def test_load_returns_defaults_when_no_file(tmp_path, monkeypatch):
    missing = tmp_path / "nonexistent" / "config.toml"
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", missing)
    cfg = UserConfig.load()
    assert cfg.home_neighbourhood == ""
    assert cfg.default_horizon_days == 14
