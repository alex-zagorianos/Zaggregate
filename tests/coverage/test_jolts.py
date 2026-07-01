import coverage.jolts as J


def test_no_key_returns_skip():
    assert J.jolts_gate("Ohio", None, 100).verdict == "skip"


def test_substate_area_skips_before_fetch(monkeypatch):
    # A metro is sub-state -> BLS has no official JOLTS -> honest skip, and the
    # network fetch is never attempted (the old code silently queried national).
    called = {"n": 0}
    def _boom(*a, **k):
        called["n"] += 1
        return 1000
    monkeypatch.setattr(J, "_fetch_expected_openings", _boom)
    assert J.jolts_gate("Cincinnati, OH", None, 100, api_key="k").verdict == "skip"
    assert called["n"] == 0


def test_network_error_returns_skip(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    assert J.jolts_gate("Ohio", None, 100, api_key="k").verdict == "skip"


def test_ratio_in_band_pass(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: 1000)
    r = J.jolts_gate("Ohio", None, 100, api_key="k")
    assert r.verdict == "pass" and r.expected_openings == 1000


def test_ratio_out_of_band_fail(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: 10)
    assert J.jolts_gate("Ohio", None, 100000, api_key="k").verdict == "fail"


def test_zero_expected_returns_skip(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: 0)
    assert J.jolts_gate("Ohio", None, 100, api_key="k").verdict == "skip"


def test_series_id_state_vs_substate():
    # Whole state -> a 21-char JTS...JOL level series carrying the state FIPS.
    sid = J._series_id("Ohio", None)
    assert sid is not None and len(sid) == 21
    assert sid.startswith("JTS") and sid.endswith("JOL")
    assert "39" in sid                      # Ohio FIPS
    assert J._series_id("OH", None) == sid  # abbrev resolves the same
    # Sub-state / unknown -> None (gate will skip).
    assert J._series_id("Cincinnati", None) is None
    assert J._series_id("Cincinnati, OH", None) is None
    assert J._series_id("", None) is None