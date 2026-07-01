"""Opt-in auto-rank in daily_run (C2 / review P4 item 7).

Off by default; runs only when (auto_rank flag) AND (a key OR base_url) are set;
a backend failure never propagates; applied scores are source='api' + undoable.
"""
import json

import pytest

import config
import daily_run
import ranker
import tracker.db as db
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


@pytest.fixture(autouse=True)
def _no_ambient_backend(monkeypatch):
    # Neutralize any real env-configured backend so gating is deterministic.
    monkeypatch.setattr(ranker, "has_api_key", lambda: False)
    monkeypatch.setattr(config, "anthropic_base_url", lambda: None)
    monkeypatch.setattr(config, "AUTO_RANK", False)


def _seed(n=2):
    jobs = [JobResult(title=f"Controls Engineer {i}", company=f"Co{i}",
                      location="Cincinnati, OH", salary_min=90000, salary_max=120000,
                      description="PLC C++ motion control", url=f"https://x/{i}",
                      source_keyword="", created="2026-06-01", source_api="adzuna",
                      score=70 + i) for i in range(n)]
    db.inbox_add_many(jobs)


def _fake_reply_for_unscored():
    """A reply scoring every currently-unscored inbox row by its token."""
    import claude_bridge
    from tracker import service
    rows = [r for r in db.inbox_all() if (r.get("fit", -1) or -1) < 0]
    jobs = service.jobs_from_rows(rows)
    return json.dumps([{"token": claude_bridge.fit_token(j), "fit": 85, "why": "ok"}
                       for j in jobs])


def test_auto_rank_off_by_default(tmp_db, monkeypatch):
    _seed()
    called = []
    monkeypatch.setattr(daily_run, "_run_api_prompt", lambda p: called.append(p) or "[]")
    daily_run._maybe_auto_rank({})                 # no auto_rank flag
    assert called == []
    assert all(r["fit"] == -1 for r in db.inbox_all())


def test_auto_rank_flag_but_no_backend_skips(tmp_db, monkeypatch):
    _seed()
    called = []
    monkeypatch.setattr(daily_run, "_run_api_prompt", lambda p: called.append(p) or "[]")
    daily_run._maybe_auto_rank({"auto_rank": True})  # flag on, but no key/base_url
    assert called == []
    assert all(r["fit"] == -1 for r in db.inbox_all())


def test_auto_rank_runs_with_flag_and_key(tmp_db, monkeypatch):
    _seed()
    monkeypatch.setattr(ranker, "has_api_key", lambda: True)
    monkeypatch.setattr(daily_run, "_run_api_prompt",
                        lambda p: _fake_reply_for_unscored())
    daily_run._maybe_auto_rank({"auto_rank": True})
    assert all(r["fit"] == 85 for r in db.inbox_all())
    # source='api' + one batch -> undo('any') reverts it.
    from tracker import service
    assert service.undo_last_rerank("any") == 2


def test_auto_rank_runs_with_base_url_only(tmp_db, monkeypatch):
    """A local model (base_url) with no API key still qualifies as a backend."""
    _seed(1)
    monkeypatch.setattr(config, "anthropic_base_url", lambda: "http://localhost:11434")
    monkeypatch.setattr(ranker, "api_key", lambda: None)
    monkeypatch.setattr(daily_run, "_run_api_prompt",
                        lambda p: _fake_reply_for_unscored())
    daily_run._maybe_auto_rank({"auto_rank": True})
    assert all(r["fit"] == 85 for r in db.inbox_all())


def test_auto_rank_backend_failure_never_raises(tmp_db, monkeypatch):
    _seed()
    monkeypatch.setattr(ranker, "has_api_key", lambda: True)

    def boom(_p):
        raise RuntimeError("backend down")

    monkeypatch.setattr(daily_run, "_run_api_prompt", boom)
    # Must swallow the error (never propagate to the daily run).
    daily_run._maybe_auto_rank({"auto_rank": True})
    assert all(r["fit"] == -1 for r in db.inbox_all())


def test_auto_rank_env_flag_enables(tmp_db, monkeypatch):
    _seed(1)
    monkeypatch.setattr(config, "AUTO_RANK", True)   # env-equivalent
    monkeypatch.setattr(ranker, "has_api_key", lambda: True)
    monkeypatch.setattr(daily_run, "_run_api_prompt",
                        lambda p: _fake_reply_for_unscored())
    daily_run._maybe_auto_rank({})                   # no cfg flag, env on
    assert all(r["fit"] == 85 for r in db.inbox_all())
