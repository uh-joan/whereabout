from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

from whereabout.sources.resident_advisor import RASource, _extract_postcode, _parse_local_dt, _parse_lineup
from whereabout.models import Query

FIXTURE = Path(__file__).parent / "fixtures" / "ra_london_synthetic.json"


@pytest.fixture
def listings():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def source():
    return RASource()


@pytest.fixture
def query():
    now = datetime.now(timezone.utc)
    return Query(
        raw_text="jazz in camden",
        genres=["jazz"],
        neighbourhood="Camden",
        date_range_start_utc=now,
        date_range_end_utc=now + timedelta(days=14),
    )


# ── postcode extraction ───────────────────────────────────────────────────────

def test_extract_postcode_clean():
    assert _extract_postcode("5 Parkway, Camden Town, London NW1 7PG") == "NW1 7PG"


def test_extract_postcode_semicolon_format():
    assert _extract_postcode("261 Brixton Road; Brixton; London SW9 6LH; United Kingdom") == "SW9 6LH"


def test_extract_postcode_inline():
    assert _extract_postcode("London EC2A 3AY") == "EC2A 3AY"


def test_extract_postcode_at_end():
    assert _extract_postcode("Londonewcastle Project Space, E8 3RL") == "E8 3RL"


def test_extract_postcode_missing():
    assert _extract_postcode("London") is None


def test_extract_postcode_empty():
    assert _extract_postcode("") is None


# ── datetime parsing ──────────────────────────────────────────────────────────

def test_parse_local_dt_returns_utc():
    dt = _parse_local_dt("2026-05-23T21:00:00.000")
    assert dt.tzinfo == timezone.utc
    # BST = UTC+1, so 21:00 local → 20:00 UTC
    assert dt.hour == 20


# ── listing → RawEvent ────────────────────────────────────────────────────────

def test_parse_camden_event(source, listings):
    raw = source._parse_listing(listings[0])
    assert raw.source == "resident_advisor"
    assert raw.title == "Yussef Dayes Trio"
    assert raw.venue_name == "Jazz Cafe Camden"
    assert raw.venue_postcode == "NW1 7PG"
    assert raw.artists == ["Yussef Dayes"]
    assert "Jazz" in raw.genres_raw
    assert raw.price_text == "£22"
    assert raw.source_url == "https://ra.co/events/uk/london/venue/jazz-cafe/yussef-dayes-2446033"
    assert raw.date_end_utc is not None


def test_parse_brixton_event(source, listings):
    raw = source._parse_listing(listings[2])
    assert raw.venue_postcode == "SW2 1DF"
    assert raw.artists == ["DJ Kojey"]
    assert "Soul" in raw.genres_raw


def test_parse_dalston_event_multiple_artists(source, listings):
    raw = source._parse_listing(listings[3])
    assert raw.venue_postcode == "E8 3RL"
    assert set(raw.artists) == {"Objekt", "Mor Elian"}


def test_parse_event_no_postcode(source, listings):
    raw = source._parse_listing(listings[4])
    assert raw.venue_postcode is None
    assert raw.artists == []
    assert raw.price_text is None


def test_parse_event_no_end_time(source, listings):
    raw = source._parse_listing(listings[1])
    assert raw.date_end_utc is None


# ── lineup parsing ────────────────────────────────────────────────────────────

def test_parse_lineup_xml_tags():
    assert _parse_lineup('<artist id="1">Objekt</artist>') == ["Objekt"]


def test_parse_lineup_xml_multiple():
    result = _parse_lineup('<artist id="1">Objekt</artist>\n<artist id="2">Mor Elian</artist>')
    assert result == ["Objekt", "Mor Elian"]


def test_parse_lineup_plain_text_with_paren():
    assert _parse_lineup("KDN (Kongo Dia Ntotila)") == ["KDN"]


def test_parse_lineup_plain_text_multiple():
    result = _parse_lineup("DJ A, DJ B & DJ C")
    assert result == ["DJ A", "DJ B", "DJ C"]


def test_parse_lineup_b2b():
    assert _parse_lineup("Objekt b2b Mor Elian") == ["Objekt", "Mor Elian"]


def test_parse_lineup_empty():
    assert _parse_lineup("") == []


def test_parse_lineup_used_when_artists_empty(source, listings):
    """listings[5] has artists=[] and lineup='KDN (Kongo Dia Ntotila)'."""
    raw = source._parse_listing(listings[5])
    assert raw.artists == ["KDN"]
    assert raw.venue_postcode == "E8 4AE"


# ── full batch parse ──────────────────────────────────────────────────────────

def test_parse_all_listings(source, listings):
    raws = [source._parse_listing(l) for l in listings]
    assert len(raws) == 6
    assert all(r.source == "resident_advisor" for r in raws)
    # 5 of 6 have postcodes
    with_postcode = [r for r in raws if r.venue_postcode]
    assert len(with_postcode) == 5
