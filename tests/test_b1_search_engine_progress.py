"""B1: SearchEngine progress-callback + cancel-event seams (additive, no network).

The GUI needs determinate per-source progress and a Cancel that stops the run
between clients/keywords. Both are additive params on run_full_search; default
None must be byte-identical to today's behavior.
"""
import threading

from search.search_engine import SearchEngine
from models import JobResult


def _job(url, title="t", company="c"):
    return JobResult(
        title=title, company=company, location="", salary_min=None,
        salary_max=None, description="", url=url, source_keyword="k",
        created="2026-06-01", job_id="", source_api="adzuna",
    )


class _Stub:
    """A minimal client: returns its jobs on page 1, honoring a per-page barrier
    so a test can control timing when needed."""
    def __init__(self, name, jobs):
        self._jobs = jobs
        # give the stub a distinct class name so the engine's per-source keying
        # (type(client).__name__) separates instances.
        self.__class__ = type(name, (_Stub,), {})

    def search_and_parse(self, keyword, location, salary_min, page):
        return self._jobs if page == 1 else []


def _stub(name, jobs):
    s = _Stub.__new__(type(name, (_Stub,), {}))
    s._jobs = jobs
    return s


# ── default behavior unchanged ────────────────────────────────────────────────

def test_no_progress_no_cancel_matches_today():
    eng = SearchEngine([_stub("Src", [_job("u1"), _job("u2")])])
    out = eng.run_full_search(["k"], max_pages_per_keyword=1)
    assert {j.url for j in out} == {"u1", "u2"}


# ── progress callback ─────────────────────────────────────────────────────────

def test_progress_emits_start_source_and_done_events():
    events = []
    eng = SearchEngine([_stub("Alpha", [_job("a1")]),
                        _stub("Beta", [_job("b1"), _job("b2")])])
    eng.run_full_search(["k"], max_pages_per_keyword=1,
                        progress=events.append)
    phases = [e["phase"] for e in events]
    assert phases[0] == "start"
    assert phases[-1] == "done"
    assert phases.count("source_done") == 2   # one per distinct source
    start = next(e for e in events if e["phase"] == "start")
    assert start["total"] == 2
    done = [e for e in events if e["phase"] == "source_done"]
    # done counter reaches total
    assert max(e["done"] for e in done) == 2
    assert all(e["total"] == 2 for e in done)
    # per-source counts are reported
    by_src = {e["source"]: e["count"] for e in done}
    assert by_src["Beta"] == 2 and by_src["Alpha"] == 1


def test_progress_callback_exception_never_breaks_search():
    def boom(_event):
        raise RuntimeError("ui thread hiccup")
    eng = SearchEngine([_stub("Src", [_job("u1")])])
    out = eng.run_full_search(["k"], max_pages_per_keyword=1, progress=boom)
    assert [j.url for j in out] == ["u1"]


def test_source_failure_reports_ok_false_with_error():
    class Boom:
        def search_and_parse(self, keyword, location, salary_min, page):
            raise ValueError("429 too many")
    events = []
    eng = SearchEngine([Boom()])
    eng.run_full_search(["k"], max_pages_per_keyword=1, progress=events.append)
    done = [e for e in events if e["phase"] == "source_done"]
    assert done and done[0]["ok"] is False
    assert "429" in done[0]["error"]


# ── cancel event ──────────────────────────────────────────────────────────────

def test_cancel_set_before_run_returns_no_new_work():
    cancel = threading.Event()
    cancel.set()
    eng = SearchEngine([_stub("Src", [_job("u1"), _job("u2")])])
    out = eng.run_full_search(["k1", "k2"], max_pages_per_keyword=2,
                              cancel=cancel)
    # Cancelled before the loop even starts -> the client yields nothing.
    assert out == []


def test_run_client_stops_between_keywords_when_cancelled():
    cancel = threading.Event()

    class Counter:
        def __init__(self):
            self.calls = 0
        def search_and_parse(self, keyword, location, salary_min, page):
            self.calls += 1
            cancel.set()               # cancel after the first fetch
            return [_job(f"u{self.calls}")]

    c = Counter()
    eng = SearchEngine([c])
    eng.run_full_search(["k1", "k2", "k3"], max_pages_per_keyword=1,
                        cancel=cancel)
    # First keyword fetched (1 call); cancel stops the remaining keywords/pages.
    assert c.calls == 1
