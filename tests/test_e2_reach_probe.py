"""E2 SerpApi reach probe wiring + badge hint.

Covers: probe merges into BOTH the scored results and engine.last_raw_results
(so estimate_reach sees the overlap); the quota-respecting SerpApiClient is used;
a probe failure never raises out of the helper; disabled/keyless -> no-op; and the
badge hint names the SerpApi unlock only when no key is present. No network — the
SerpApiClient is faked."""
import pytest

import daily_run
from models import JobResult


class _FakeEngine:
    def __init__(self, raw):
        self.last_raw_results = list(raw)


def _job(title, company, src="serpapi"):
    return JobResult(
        title=title, company=company, location="Cincinnati, OH",
        salary_min=None, salary_max=None, description="", url=f"http://x/{title}",
        source_keyword="nurse", created="", job_id=f"{src}_{title}", source_api=src)


class _FakeSerpApi:
    """Stands in for SerpApiClient: records the queries it was asked and returns a
    canned job per query."""
    def __init__(self, *a, **k):
        self.queries = []

    def search_and_parse(self, keyword, location, salary_min, page):
        self.queries.append((keyword, location, page))
        return [_job(f"probe-{keyword}", "SerpCo")]


@pytest.fixture
def _patch_serpapi(monkeypatch):
    fake = _FakeSerpApi()
    import search.serpapi_client as SC
    monkeypatch.setattr(SC, "SerpApiClient", lambda *a, **k: fake)
    # Keep daily_run's log quiet-ish (still exercises it).
    monkeypatch.setattr(daily_run, "log", lambda *a, **k: None)
    return fake


def test_probe_merges_into_results_and_raw(_patch_serpapi, monkeypatch):
    monkeypatch.setattr("config.REACH_PROBE", True)
    engine = _FakeEngine([_job("existing", "AcmeHealth", src="careers")])
    results = [_job("existing", "AcmeHealth", src="careers")]
    merged = daily_run._reach_probe(
        engine, results, keywords=["nurse", "registered nurse practitioner"],
        location="Cincinnati, OH", cfg={"reach_probe_queries": 1})
    assert merged == 1
    # Merged into BOTH lists.
    assert any(j.source_api == "serpapi" for j in results)
    assert any(j.source_api == "serpapi" for j in engine.last_raw_results)
    # Broadest (shortest) keyword chosen: "nurse".
    assert _patch_serpapi.queries[0][0] == "nurse"


def test_probe_respects_query_budget(_patch_serpapi, monkeypatch):
    monkeypatch.setattr("config.REACH_PROBE", True)
    engine = _FakeEngine([])
    results = []
    daily_run._reach_probe(engine, results, keywords=["a", "bb", "ccc", "dddd"],
                           location="", cfg={"reach_probe_queries": 2})
    assert len(_patch_serpapi.queries) == 2  # capped at budget


def test_probe_noop_when_disabled(_patch_serpapi, monkeypatch):
    engine = _FakeEngine([])
    results = []
    merged = daily_run._reach_probe(engine, results, keywords=["nurse"],
                                    location="", cfg={"reach_probe": False})
    assert merged == 0
    assert results == []
    assert _patch_serpapi.queries == []  # SerpApiClient never even built


def test_probe_noop_without_key(monkeypatch):
    monkeypatch.setattr("config.REACH_PROBE", True)

    def _raise(*a, **k):
        raise ValueError("SerpApi key missing")

    import search.serpapi_client as SC
    monkeypatch.setattr(SC, "SerpApiClient", _raise)
    monkeypatch.setattr(daily_run, "log", lambda *a, **k: None)
    engine = _FakeEngine([])
    results = []
    assert daily_run._reach_probe(engine, results, keywords=["nurse"],
                                  location="", cfg={}) == 0
    assert results == []


def test_probe_failure_never_raises(monkeypatch):
    monkeypatch.setattr("config.REACH_PROBE", True)

    class _Boom:
        def __init__(self, *a, **k):
            pass

        def search_and_parse(self, **k):
            raise RuntimeError("network blip")

    import search.serpapi_client as SC
    monkeypatch.setattr(SC, "SerpApiClient", _Boom)
    monkeypatch.setattr(daily_run, "log", lambda *a, **k: None)
    engine = _FakeEngine([])
    results = []
    # A per-query failure is swallowed; helper returns 0, does not raise.
    assert daily_run._reach_probe(engine, results, keywords=["nurse"],
                                  location="", cfg={}) == 0


# ── badge hint ────────────────────────────────────────────────────────────────
def test_badge_hint_when_no_serpapi_key(monkeypatch):
    from coverage import reach
    monkeypatch.setattr(reach, "_serpapi_key_present", lambda: False)
    snap = {"certifiable": False, "n_distinct": 40, "n_families": 3}
    line = reach.badge_line(snap)
    assert "not yet certifiable" in line
    assert "SerpApi" in line


def test_badge_no_hint_when_key_present(monkeypatch):
    from coverage import reach
    monkeypatch.setattr(reach, "_serpapi_key_present", lambda: True)
    snap = {"certifiable": False, "n_distinct": 40, "n_families": 3}
    line = reach.badge_line(snap)
    assert "not yet certifiable" in line
    assert "SerpApi" not in line


def test_badge_certifiable_unchanged(monkeypatch):
    from coverage import reach
    monkeypatch.setattr(reach, "_serpapi_key_present", lambda: False)
    snap = {"certifiable": True, "coverage_pct": 82.0, "coverage_ci": [70.0, 95.0],
            "n_distinct": 40, "n_families": 3}
    line = reach.badge_line(snap)
    assert "82%" in line
    assert "SerpApi" not in line  # hint only on the non-certifiable branch


def test_reach_probe_enabled_config():
    import config
    assert config.reach_probe_enabled({"reach_probe": False}) is False
    assert config.reach_probe_enabled({"reach_probe": True}) is True
    # Absent key -> falls back to the module default (REACH_PROBE, default ON).
    assert config.reach_probe_enabled({}) == config.REACH_PROBE
