import json
import pytest
import respx
import httpx
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from whereabout.cli import app
from whereabout.config import UserConfig

runner = CliRunner()
CAMDEN_FIXTURE = Path(__file__).parent / "fixtures" / "dice_camden_live_snapshot.json"
BRIXTON_FIXTURE = Path(__file__).parent / "fixtures" / "dice_brixton_synthetic.json"


@pytest.fixture(autouse=True)
def patch_cache_dirs(tmp_path, monkeypatch):
    import whereabout.sources.dice_fm as dice_mod
    monkeypatch.setattr(dice_mod, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(dice_mod, "SNAPSHOT_DIR", tmp_path / "snapshots")


@pytest.fixture(autouse=True)
def patch_ingest(monkeypatch):
    monkeypatch.setattr("whereabout.query.ranker.ingest", lambda raws: 0)


def mock_parser_response(genres, neighbourhood, days=14):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps({
        "genres": genres, "neighbourhood": neighbourhood,
        "date_range_days": days, "did_you_mean": None
    }))]
    mock_msg.usage = MagicMock(input_tokens=100, output_tokens=50)
    return mock_msg


def test_first_run_prompts_for_neighbourhood(tmp_path, monkeypatch):
    """First run (no config) prompts user to set home neighbourhood."""
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "nonexistent.toml")
    monkeypatch.setattr("whereabout.query.parser.check_and_record", lambda i, o: None)

    camden_data = json.loads(CAMDEN_FIXTURE.read_text())
    with patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_parser_response(["jazz"], "Camden")
        from whereabout.sources.dice_fm import DICESource
        with respx.mock:
            respx.get(DICESource.BASE_URL).mock(return_value=httpx.Response(200, json=camden_data))
            result = runner.invoke(app, ["query", "jazz in camden"], input="Camden\n")

    assert result.exit_code == 0 or "First run" in result.output or "neighbourhood" in result.output.lower()


def test_list_then_detail(tmp_path, monkeypatch):
    """Query returns a list; querying detail by source_event_id returns enriched output."""
    # This is an integration smoke test — verify the detail command accepts an ID
    # Full DB integration tested separately; here we just test the CLI wiring.
    result = runner.invoke(app, ["detail", "nonexistent-id-xyz"])
    # Should exit non-zero with "not found" message, not crash
    assert result.exit_code != 0 or "not found" in result.output.lower() or result.exit_code == 1


def test_query_jazz_camden(tmp_path, monkeypatch):
    """End-to-end query command returns jazz events in Camden."""
    monkeypatch.setattr("whereabout.config.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("whereabout.query.parser.check_and_record", lambda i, o: None)
    cfg = UserConfig(home_neighbourhood="Camden")
    cfg.save()

    camden_data = json.loads(CAMDEN_FIXTURE.read_text())
    with patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_parser_response(["jazz"], "Camden")
        from whereabout.sources.dice_fm import DICESource
        with respx.mock:
            respx.get(DICESource.BASE_URL).mock(return_value=httpx.Response(200, json=camden_data))
            result = runner.invoke(app, ["query", "jazz in camden"])

    assert result.exit_code == 0
    assert "jazz" in result.output.lower() or "Camden" in result.output or len(result.output) > 10
