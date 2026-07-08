"""Live yield probe (probe.py) -- budget math, date rollover, and pool
recording, all offline. The real Adzuna network call (``_adzuna_count``) is
monkeypatched in every test; the autouse conftest socket guard would fail
loudly if any test accidentally reached it for real."""
import pytest

import config
import workspace
from tracker import db
from search.discovery import pool, probe


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    # probe.py persists its daily counter under workspace.project_dir(slug) --
    # repoint it at the temp dir so the JSON file never touches real user data.
    monkeypatch.setattr(workspace, "project_dir", lambda slug=None: tmp_path)
    return tmp_path


def test_probe_records_yield_and_decrements_budget(tmp_project, monkeypatch):
    pool.upsert_terms([{"term": "Welder", "tier": "core", "source": "onet"}])
    monkeypatch.setattr(probe, "_adzuna_count", lambda term, location="": 42)

    assert probe.probes_remaining(today="2026-07-08") == 10
    result = probe.probe_yield("Welder", "Cincinnati, OH", today="2026-07-08")

    assert result == {
        "term": "Welder",
        "yield_count": 42,
        "yield_source": "adzuna:Cincinnati, OH",
        "probes_remaining_today": 9,
        "skipped": False,
        "reason": "",
    }
    row = pool.get_term("Welder")
    assert row["yield_count"] == 42
    assert row["yield_source"] == "adzuna:Cincinnati, OH"


def test_probe_budget_caps_at_10_per_day(tmp_project, monkeypatch):
    calls = []
    monkeypatch.setattr(
        probe, "_adzuna_count",
        lambda term, location="": calls.append(term) or 5,
    )

    for i in range(10):
        result = probe.probe_yield(f"term-{i}", today="2026-07-08")
        assert result["skipped"] is False

    eleventh = probe.probe_yield("term-10", today="2026-07-08")
    assert eleventh["skipped"] is True
    assert eleventh["reason"] == "budget"
    assert eleventh["yield_count"] is None
    assert len(calls) <= 10


def test_probe_budget_resets_next_day(tmp_project, monkeypatch):
    monkeypatch.setattr(probe, "_adzuna_count", lambda term, location="": 1)
    for i in range(10):
        probe.probe_yield(f"term-{i}", today="2026-01-01")
    assert probe.probes_remaining(today="2026-01-01") == 0

    # a later date rolls the counter over, even without a fresh write in between
    assert probe.probes_remaining(today="2026-01-02") == 10
    result = probe.probe_yield("term-fresh", today="2026-01-02")
    assert result["skipped"] is False
    assert result["probes_remaining_today"] == 9


def test_probe_no_key_skips_gracefully(tmp_project, monkeypatch):
    monkeypatch.setattr(config, "resolve_secret", lambda *a, **k: None)

    def _boom(*a, **k):
        raise AssertionError("_adzuna_count must not be called when unconfigured")

    monkeypatch.setattr(probe, "_adzuna_count", _boom)

    result = probe.probe_yield("Welder", today="2026-07-08")
    assert result == {
        "term": "Welder",
        "yield_count": None,
        "yield_source": "",
        "probes_remaining_today": 10,
        "skipped": True,
        "reason": "no_key",
    }
    # a no_key skip never reached the network -> budget untouched
    assert probe.probes_remaining(today="2026-07-08") == 10


def test_probe_network_error_never_raises(tmp_project, monkeypatch):
    def _boom(term, location=""):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(probe, "_adzuna_count", _boom)

    result = probe.probe_yield("Welder", today="2026-07-08")
    assert result["skipped"] is True
    assert result["reason"] == "error"
    assert result["yield_count"] is None
    # an attempted-but-failed probe still spent a real Adzuna hit
    assert result["probes_remaining_today"] == 9


def test_probe_terms_stops_at_budget(tmp_project, monkeypatch):
    calls = []
    monkeypatch.setattr(
        probe, "_adzuna_count",
        lambda term, location="": calls.append(term) or 3,
    )
    results = probe.probe_terms([f"t{i}" for i in range(15)], "Cincinnati, OH")
    assert len(results) == 15
    assert sum(1 for r in results if not r["skipped"]) == 10
    assert sum(1 for r in results if r["reason"] == "budget") == 5
    assert len(calls) == 10


def test_probe_limiter_matches_adzuna_rate_ceiling():
    # No process-wide AdzunaClient limiter exists to reuse -- every call site
    # (source_registry.py, ui/source_keys_core.py) builds its OWN client
    # instance, so there's no live limiter object this module can share
    # without editing adzuna_client.py. This pins the plan's stated fallback:
    # a same-rate, same-process singleton (not true cross-process sharing).
    limiter_a = probe._limiter()
    limiter_b = probe._limiter()
    assert limiter_a is limiter_b
    assert limiter_a.max == config.ADZUNA_RATE_LIMIT
