import json
import pytest
import respx
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from whereabout.query.ranker import rank
from whereabout.models import Query

BRIXTON_FIXTURE = Path(__file__).parent / "fixtures" / "dice_brixton_synthetic.json"


@pytest.fixture(autouse=True)
def patch_ingest(monkeypatch):
    """Don't write to real DB during ranker tests."""
    monkeypatch.setattr("whereabout.query.ranker.ingest", lambda raws: 0)


@pytest.fixture(autouse=True)
def patch_cache_dirs(tmp_path, monkeypatch):
    import whereabout.sources.dice_fm as dice_mod
    monkeypatch.setattr(dice_mod, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(dice_mod, "SNAPSHOT_DIR", tmp_path / "snapshots")


def test_brixton_excludes_clapham():
    """
    Synthetic Brixton fixture: all 5 events are in SW2/SW9.
    A Clapham (SW4) event injected into the response must be excluded.
    NOTE: DICE Brixton coverage is sparse in production; live demos use Camden/Dalston.
    This test uses synthetic fixtures to validate neighbourhood filtering logic.
    """
    fixture_data = json.loads(BRIXTON_FIXTURE.read_text())
    # Inject a Clapham event that must be filtered out
    clapham_event = {
        "id": "clapham-001",
        "name": "Clapham Gig (should be excluded)",
        "date": "2026-06-07T20:00:00Z",
        "artists": [{"name": "Clapham Band"}],
        "venues": [{"name": "The Clapham Grand"}],
        "address": "21 St John's Hill, London SW11 1TT",
        "location": {"zip": "SW11 1TT", "lat": 51.4614, "lng": -0.1674},
        "genre_tags": ["jazz"],
        "url": "https://dice.fm/event/clapham-001",
        "ticket_types": [{"price": {"total": 1000}}],
    }
    fixture_data["data"].append(clapham_event)

    now = datetime.now(timezone.utc)
    query = Query(
        raw_text="jazz in brixton",
        genres=["jazz"],
        neighbourhood="Brixton",
        date_range_start_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        date_range_end_utc=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )

    with respx.mock:
        from whereabout.sources.dice_fm import DICESource
        respx.get(DICESource.BASE_URL).mock(
            return_value=httpx.Response(200, json=fixture_data)
        )
        results = rank(query)

    # All results must be Brixton (SW2 or SW9), not Clapham (SW11)
    assert len(results) >= 1
    assert all("Clapham" not in r["title"] for r in results)
    assert all("SW11" not in r.get("postcode", "") for r in results)
