from whereabout.doctor import run_checks


def test_run_checks_returns_five_items():
    results = run_checks()
    assert len(results) == 5


def test_run_checks_returns_tuples():
    results = run_checks()
    for passed, msg in results:
        assert isinstance(passed, bool)
        assert isinstance(msg, str)
        assert len(msg) > 0
