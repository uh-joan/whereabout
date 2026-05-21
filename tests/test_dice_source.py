import json
import pytest
import respx
import httpx
from pathlib import Path
from datetime import datetime, timezone, timedelta
from whereabout.sources.dice_fm import DICESource
from whereabout.models import Query

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dice_brixton_synthetic.json"


@pytest.fixture
def brixton_fixture():
    return json.loads(FIXTURE_PATH.read_text())


@pytest.mark.asyncio
async def test_parse_synthetic_brixton(brixton_fixture, tmp_path, monkeypatch):
    """Parse synthetic Brixton fixture with no network calls."""
    import whereabout.sources.dice_fm as dice_mod
    monkeypatch.setattr(dice_mod, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(dice_mod, "SNAPSHOT_DIR", tmp_path / "snapshots")

    source = DICESource()
    now = datetime.now(timezone.utc)
    query = Query(
        raw_text="jazz in brixton",
        genres=["jazz"],
        neighbourhood="Brixton",
        date_range_start_utc=now,
        date_range_end_utc=now + timedelta(days=14),
    )

    with respx.mock:
        respx.get(DICESource.BASE_URL).mock(
            return_value=httpx.Response(200, json=brixton_fixture)
        )
        events = await source.fetch(query)

    assert len(events) == 5
    assert all(e.source == "dice_fm" for e in events)
    assert all(e.date_start_utc.tzinfo is not None for e in events)
    sw2_or_sw9 = [e for e in events if e.venue_postcode and e.venue_postcode.startswith(("SW2", "SW9"))]
    assert len(sw2_or_sw9) == 5
