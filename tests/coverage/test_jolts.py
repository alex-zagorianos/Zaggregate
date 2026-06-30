import coverage.jolts as J

def test_no_key_returns_skip():
    assert J.jolts_gate("Cincinnati, OH", None, 100).verdict == "skip"

def test_network_error_returns_skip(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    assert J.jolts_gate("X", None, 100, api_key="k").verdict == "skip"

def test_ratio_in_band_pass(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: 1000)
    r = J.jolts_gate("X", None, 100, api_key="k")
    assert r.verdict == "pass" and r.expected_openings == 1000

def test_ratio_out_of_band_fail(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: 10)
    assert J.jolts_gate("X", None, 100000, api_key="k").verdict == "fail"

def test_zero_expected_returns_skip(monkeypatch):
    monkeypatch.setattr(J, "_fetch_expected_openings", lambda *a, **k: 0)
    assert J.jolts_gate("X", None, 100, api_key="k").verdict == "skip"
