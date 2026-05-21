from whereabout.neighbourhoods import resolve_postcode_prefix, resolve_name, did_you_mean


def test_brixton_sw2():
    assert resolve_postcode_prefix("SW2 1AA") == "Brixton"


def test_brixton_sw9():
    assert resolve_postcode_prefix("SW9 8LF") == "Brixton"


def test_clapham_sw4():
    result = resolve_postcode_prefix("SW4 0JN")
    assert result == "Clapham"


def test_brixton_sw2_sw9():
    assert resolve_postcode_prefix("SW2") == "Brixton"
    assert resolve_postcode_prefix("SW9") == "Brixton"


def test_did_you_mean_streatham_hill():
    suggestions = did_you_mean("Streatham Hill")
    assert len(suggestions) > 0
    # Should suggest Streatham
    assert any("Streatham" in s for s in suggestions)


def test_ward_aliases_brixton_windrush():
    assert resolve_name("Brixton Windrush") == "Brixton"


def test_unknown_returns_none():
    assert resolve_postcode_prefix("ZZ99") is None
