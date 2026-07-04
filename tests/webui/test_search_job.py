"""Tk-free search core (search.search_job.run_search) — the seam the web Search job
wraps. Proves it (a) builds clients honoring source toggles / keyless-skip, (b) runs
the engine with progress+cancel, (c) classifies per-source health via the shared
core, and (d) calls match.scorer.score_jobs with the SAME kwargs the tk
SearchTab._worker uses (scoring parity — no drift, no scorer touched).
"""
import threading

import pytest

import search.search_job as sj
from models import JobResult


def _jr(url="https://x/1", **kw):
    base = dict(title="Eng", company="Acme", location="Remote", salary_min=None,
                salary_max=None, description="d", url=url, source_keyword="eng",
                created="2026-07-01", job_id="", source_api="adzuna")
    base.update(kw)
    return JobResult(**base)


@pytest.fixture
def _stub_engine(monkeypatch):
    """Stub build_clients (one dummy client, honoring skipped_keyless) + a fake
    SearchEngine that replays scripted progress events and returns given rows."""
    scripted = {"events": [], "rows": []}

    def fake_build_clients(sources, **kw):
        sk = kw.get("skipped_keyless")
        for s in scripted.get("keyless", []):
            if sk is not None:
                sk.append(s)

        class _C:
            pass
        return [_C()]

    class _FakeEngine:
        def __init__(self, clients):
            pass

        def run_full_search(self, *, keywords, location, salary_min,
                            max_pages_per_keyword=2, progress=None, cancel=None):
            scripted["seen_keywords"] = keywords
            for ev in scripted["events"]:
                progress(ev)
            return list(scripted["rows"])

    monkeypatch.setattr("search.cli.build_clients", fake_build_clients)
    monkeypatch.setattr("search.cli.ALL_SOURCES",
                        ["adzuna", "jsearch", "careeronestop"], raising=False)
    monkeypatch.setattr("search.search_engine.SearchEngine", _FakeEngine)
    # score_jobs + seen_urls are captured / neutralized.
    calls = {}
    monkeypatch.setattr("match.scorer.score_jobs",
                        lambda results, **kw: calls.setdefault("score_kw", kw))
    monkeypatch.setattr("tracker.db.seen_urls", lambda: set())
    scripted["calls"] = calls
    return scripted


def test_run_search_classifies_health(_stub_engine):
    _stub_engine["events"] = [
        {"phase": "start", "total": 3},
        {"phase": "source_done", "source": "AdzunaClient", "count": 5, "ok": True,
         "error": "", "done": 1, "total": 3},
        {"phase": "source_done", "source": "JSearchClient", "count": 0, "ok": False,
         "error": "429", "done": 2, "total": 3},
        {"phase": "source_done", "source": "CareerOneStopClient", "count": 0,
         "ok": False, "error": "", "done": 3, "total": 3},
    ]
    _stub_engine["keyless"] = ["careeronestop"]
    _stub_engine["rows"] = [_jr()]

    events_seen = []
    results, health = sj.run_search(
        ["engineer"], "Remote", None,
        user_cfg={"industry": ""}, hide_tracked=True,
        on_event=events_seen.append)

    by_src = {h["source"]: h["status"] for h in health}
    assert by_src == {"AdzunaClient": "ok", "JSearchClient": "throttled",
                      "CareerOneStopClient": "keyless"}
    # on_event received the raw engine events verbatim (start + 3 source_done)
    assert [e["phase"] for e in events_seen].count("source_done") == 3
    assert events_seen[0]["phase"] == "start"


def test_run_search_scoring_kwargs_parity(_stub_engine):
    """score_jobs is called with the exact keyword set SearchTab._worker uses."""
    _stub_engine["events"] = []
    _stub_engine["rows"] = [_jr()]
    cfg = {"industry": "", "exclude_keywords": ["intern"],
           "exclude_titles": ["manager"], "title_miss_penalty": 20,
           "seniority_exclude": ["principal"], "seniority_target": "senior",
           "years_cap": 8, "title_context_required": True}
    sj.run_search(["engineer"], "Remote", 100000, user_cfg=cfg, hide_tracked=False)

    kw = _stub_engine["calls"]["score_kw"]
    assert kw["keywords"] == ["engineer"]
    assert kw["location"] == "Remote"
    assert kw["salary_floor"] == 100000
    assert kw["exclude_keywords"] == ["intern"]
    assert kw["exclude_titles"] == ["manager"]
    assert kw["title_miss_penalty"] == 20
    assert kw["seniority_exclude"] == ["principal"]
    assert kw["seniority_target"] == "senior"
    assert kw["years_cap"] == 8
    assert kw["title_context_required"] is True
    # remote flags come from preferences.load; present regardless
    assert "remote_ok" in kw and "remote_regions_ok" in kw


def test_run_search_hide_tracked_filters_seen(_stub_engine, monkeypatch):
    _stub_engine["events"] = []
    _stub_engine["rows"] = [_jr(url="https://x/seen"), _jr(url="https://x/new")]
    # seen set holds NORMALIZED urls (the real normalizer), as tracker.db.seen_urls
    # returns; the core filters via normalize_url on each result.
    from tracker.db import normalize_url
    monkeypatch.setattr("tracker.db.seen_urls",
                        lambda: {normalize_url("https://x/seen")})
    results, _ = sj.run_search(["e"], "Remote", None,
                               user_cfg={"industry": ""}, hide_tracked=True)
    assert [r.url for r in results] == ["https://x/new"]


def test_run_search_cancel_passed_through(_stub_engine, monkeypatch):
    """The cancel Event is forwarded to run_full_search unchanged."""
    seen = {}
    ev = threading.Event()

    class _E:
        def __init__(self, clients):
            pass

        def run_full_search(self, *, keywords, location, salary_min,
                            max_pages_per_keyword=2, progress=None, cancel=None):
            seen["cancel_is"] = cancel
            return []
    monkeypatch.setattr("search.search_engine.SearchEngine", _E)
    sj.run_search(["e"], "Remote", None, user_cfg={"industry": ""}, cancel=ev)
    assert seen["cancel_is"] is ev
