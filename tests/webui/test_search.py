"""Search API (Phase 4): job lifecycle w/ scripted progress, JSON-line SSE frames,
real source-health classification, cancel wiring, exclusive-vs-daily mutex, and the
track/dismiss/add-all result mutations (parity-shaped).

Two levels of fake:
* the ROUTE/mutex/frame tests monkeypatch ``search.search_job.run_search`` (the seam
  the job fn imports) so the job is deterministic with no engine;
* the CLASSIFIER tests monkeypatch ``SearchEngine.run_full_search`` to emit scripted
  progress events and let the REAL ``run_search`` classify them, asserting the health
  list is derived by the shared ``tab_search_core`` logic — no re-implementation.
"""
import json
import threading

import pytest

import workspace
from tests.webui.conftest import wait_until
from webui.jobs import runner


_LOOPBACK = "http://127.0.0.1:5002"
_H = {"Origin": _LOOPBACK}


@pytest.fixture(autouse=True)
def _reset_runner():
    with runner._lock:
        runner._jobs.clear()
        runner._active.clear()
        runner._exclusive_active = None
    yield
    with runner._lock:
        runner._jobs.clear()
        runner._active.clear()
        runner._exclusive_active = None


@pytest.fixture(autouse=True)
def _active_slug(monkeypatch):
    monkeypatch.setattr(workspace, "active_slug", lambda: "projA")


@pytest.fixture(autouse=True)
def _stub_user_cfg(monkeypatch):
    """The /search route calls search.cli.load_user_config at request time to
    resolve fallbacks; stub it so tests don't depend on a real project config."""
    import search.cli as cli
    monkeypatch.setattr(cli, "load_user_config",
                        lambda path=None: {"keywords": ["engineer"],
                                           "location": "Remote",
                                           "max_per_company": 15})


def _wait_status(client, job_id, target, timeout=3.0):
    def _check():
        snap = client.get(f"/api/jobs/{job_id}").get_json()
        return snap if snap.get("status") == target else None
    return wait_until(
        _check, timeout=timeout,
        message=f"job {job_id} never {target}: "
                f"{client.get(f'/api/jobs/{job_id}').get_json()}")


def _make_job_result(**kw):
    from models import JobResult
    base = dict(title="Sr Engineer", company="Acme", location="Remote",
                salary_min=100000, salary_max=150000, description="Build things",
                url="https://acme.example/jobs/1", source_keyword="engineer",
                created="2026-07-01", job_id="", source_api="adzuna", score=82,
                score_notes="strong title match", board_count=-1, is_new=True,
                valid_through="")
    base.update(kw)
    return JobResult(**base)


# ── lifecycle: rows + health shape ────────────────────────────────────────────

def test_search_job_result_rows_and_health(client, monkeypatch):
    """Happy path through a stubbed run_search: the job result carries serialized
    rows (all dataclass fields + salary/seen) and the per-source health list."""
    rows_in = [_make_job_result(),
               _make_job_result(title="Staff Eng", url="https://acme.example/2",
                                score=-1)]
    health_in = [{"source": "AdzunaClient", "count": 2, "ok": True, "error": "",
                  "skipped_keyless": False, "status": "ok"},
                 {"source": "JoobleClient", "count": 0, "ok": True, "error": "",
                  "skipped_keyless": True, "status": "keyless"}]

    def fake_run_search(keywords, location, salary_min, *, user_cfg,
                        hide_tracked=True, on_event=None, cancel=None):
        on_event({"phase": "start", "total": 2})
        on_event({"phase": "source_done", "source": "AdzunaClient", "count": 2,
                  "ok": True, "error": "", "done": 1, "total": 2})
        return rows_in, health_in
    monkeypatch.setattr("search.search_job.run_search", fake_run_search)
    monkeypatch.setattr("search.search_job.seen_for_urls", lambda urls: set())

    resp = client.post("/api/search", headers=_H,
                       json={"keywords": ["engineer"], "location": "Remote"})
    assert resp.status_code == 200
    jid = resp.get_json()["job_id"]
    snap = _wait_status(client, jid, "done")
    result = snap["result"]
    assert [r["title"] for r in result["rows"]] == ["Sr Engineer", "Staff Eng"]
    # full-field serialization: score, salary display, source, seen flag present
    r0 = result["rows"][0]
    assert r0["score"] == 82
    assert r0["salary"] == "$100,000 - $150,000"
    assert r0["source_api"] == "adzuna"
    assert r0["seen"] is False
    # unscored row keeps score -1 (client renders blank, like the tk tree)
    assert result["rows"][1]["score"] == -1
    assert result["health"] == health_in


def test_search_seen_flag_marks_tracked_rows(client, monkeypatch):
    """A result whose URL is already tracked/dismissed comes back seen=True."""
    row = _make_job_result(url="https://acme.example/seen")
    monkeypatch.setattr("search.search_job.run_search",
                        lambda *a, **k: ([row], []))
    monkeypatch.setattr("search.search_job.seen_for_urls",
                        lambda urls: {"https://acme.example/seen"})
    jid = client.post("/api/search", headers=_H,
                      json={"keywords": ["x"]}).get_json()["job_id"]
    snap = _wait_status(client, jid, "done")
    assert snap["result"]["rows"][0]["seen"] is True


# ── SSE JSON-line frames ──────────────────────────────────────────────────────

def test_search_sse_emits_event_frames_and_plain_summary(client, monkeypatch):
    """Structured progress is streamed as ``@event {json}`` log lines; the closing
    summary is a plain (unprefixed) line. Asserts both the frame prefix and that the
    JSON parses back to the emitted event."""
    def fake_run_search(keywords, location, salary_min, *, user_cfg,
                        hide_tracked=True, on_event=None, cancel=None):
        on_event({"phase": "start", "total": 1})
        on_event({"phase": "source_start", "source": "AdzunaClient"})
        on_event({"phase": "source_done", "source": "AdzunaClient", "count": 3,
                  "ok": True, "error": "", "done": 1, "total": 1})
        return [_make_job_result()], []
    monkeypatch.setattr("search.search_job.run_search", fake_run_search)
    monkeypatch.setattr("search.search_job.seen_for_urls", lambda urls: set())

    jid = client.post("/api/search", headers=_H,
                      json={"keywords": ["engineer"]}).get_json()["job_id"]
    _wait_status(client, jid, "done")
    text = client.get(f"/api/jobs/{jid}/events").get_data(as_text=True)

    # Every structured frame is a data: line beginning with the @event sentinel.
    from webui.api.search import EVENT_PREFIX
    event_lines = [ln[len("data: "):] for ln in text.splitlines()
                   if ln.startswith("data: " + EVENT_PREFIX)]
    assert event_lines, "no @event frames streamed"
    phases = [json.loads(ln[len(EVENT_PREFIX):])["phase"] for ln in event_lines]
    assert phases == ["start", "source_start", "source_done"]
    # The closing summary is a PLAIN line (no @event prefix).
    assert "data: 1 result(s)." in text
    assert "event: done" in text


# ── real classifier vs scripted engine events ─────────────────────────────────

def test_health_classified_by_real_core_from_scripted_events(client, monkeypatch):
    """Drive the REAL search_job.run_search with a monkeypatched
    SearchEngine.run_full_search that emits scripted source_done events, and assert
    the health list is classified by the shared tab_search_core.source_status (ok /
    throttled / keyless) — not re-implemented in the API."""
    import search.search_job as sj

    scripted = [
        {"phase": "start", "total": 3},
        {"phase": "source_done", "source": "AdzunaClient", "count": 5, "ok": True,
         "error": "", "done": 1, "total": 3},
        {"phase": "source_done", "source": "JSearchClient", "count": 0, "ok": False,
         "error": "429 Too Many Requests", "done": 2, "total": 3},
        {"phase": "source_done", "source": "CareerOneStopClient", "count": 0,
         "ok": False, "error": "401 missing key", "done": 3, "total": 3},
    ]

    class _FakeEngine:
        def __init__(self, clients):
            pass

        def run_full_search(self, *, keywords, location, salary_min,
                            max_pages_per_keyword=2, progress=None, cancel=None):
            for ev in scripted:
                progress(ev)
            return []  # no rows; classifier is what we assert

    # Build one dummy client so run_search takes the engine branch, and stub the
    # engine + client builder so no network / real sources are touched.
    monkeypatch.setattr("search.search_engine.SearchEngine", _FakeEngine)
    monkeypatch.setattr(sj, "SearchEngine", _FakeEngine, raising=False)

    def fake_build_clients(sources, **kw):
        # honor the skipped_keyless out-param so CareerOneStop is flagged keyless
        sk = kw.get("skipped_keyless")
        if sk is not None:
            sk.append("careeronestop")

        class _C:
            pass
        return [_C()]
    monkeypatch.setattr("search.cli.build_clients", fake_build_clients)
    monkeypatch.setattr("search.cli.ALL_SOURCES",
                        ["adzuna", "jsearch", "careeronestop"], raising=False)

    got = {}

    def fake_run_search_wrapper(*a, **k):
        results, health = _orig(*a, **k)
        got["health"] = health
        return results, health
    _orig = sj.run_search
    monkeypatch.setattr("search.search_job.run_search", fake_run_search_wrapper)
    monkeypatch.setattr("search.search_job.seen_for_urls", lambda urls: set())

    jid = client.post("/api/search", headers=_H,
                      json={"keywords": ["engineer"]}).get_json()["job_id"]
    _wait_status(client, jid, "done")

    by_src = {h["source"]: h["status"] for h in got["health"]}
    assert by_src["AdzunaClient"] == "ok"
    assert by_src["JSearchClient"] == "throttled"      # 429 -> throttled
    assert by_src["CareerOneStopClient"] == "keyless"  # skipped_keyless flag


# ── cancel wires the Event ────────────────────────────────────────────────────

def test_search_cancel_sets_event(client, monkeypatch):
    started = threading.Event()
    saw_cancel = {}

    def fake_run_search(keywords, location, salary_min, *, user_cfg,
                        hide_tracked=True, on_event=None, cancel=None):
        started.set()
        # cancel is a threading.Event -- .wait() blocks efficiently instead of
        # busy-polling with a real sleep.
        if cancel is not None and cancel.wait(2.0):
            saw_cancel["hit"] = True
        return [], []
    monkeypatch.setattr("search.search_job.run_search", fake_run_search)
    monkeypatch.setattr("search.search_job.seen_for_urls", lambda urls: set())

    jid = client.post("/api/search", headers=_H,
                      json={"keywords": ["x"]}).get_json()["job_id"]
    assert started.wait(2.0)
    resp = client.post(f"/api/jobs/{jid}/cancel", headers=_H)
    assert resp.get_json()["cancelled"] is True
    _wait_status(client, jid, "cancelled")
    assert saw_cancel.get("hit") is True


# ── exclusive mutex vs daily run ──────────────────────────────────────────────

def test_search_blocks_and_is_blocked_by_daily(client, monkeypatch):
    """A search job holds the process-wide exclusive engine mutex: a daily run for
    another project can't start while it's in flight, and vice-versa."""
    from webui.api import runs as runs_mod
    gate = threading.Event()

    def blocking_search(*a, **k):
        gate.wait(3.0)
        return [], []
    monkeypatch.setattr("search.search_job.run_search", blocking_search)
    monkeypatch.setattr("search.search_job.seen_for_urls", lambda urls: set())
    monkeypatch.setattr(runs_mod, "_daily_ingest", lambda slug, **k: 0)

    r1 = client.post("/api/search", headers=_H, json={"keywords": ["x"]})
    j1 = r1.get_json()["job_id"]
    try:
        # Different project's daily run must 409 on the exclusive mutex.
        monkeypatch.setattr(workspace, "active_slug", lambda: "projB")
        r2 = client.post("/api/runs/daily", headers=_H)
        assert r2.status_code == 409
        assert r2.get_json()["error"] == "another run is in progress"
        assert r2.get_json()["job_id"] == j1
    finally:
        gate.set()
    _wait_status(client, j1, "done")


def test_search_same_project_409(client, monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr("search.search_job.run_search",
                        lambda *a, **k: (gate.wait(3.0), ([], []))[1])
    monkeypatch.setattr("search.search_job.seen_for_urls", lambda urls: set())
    r1 = client.post("/api/search", headers=_H, json={"keywords": ["x"]})
    j1 = r1.get_json()["job_id"]
    try:
        r2 = client.post("/api/search", headers=_H, json={"keywords": ["x"]})
        assert r2.status_code == 409
        assert r2.get_json()["error"] == "already running"
        assert r2.get_json()["job_id"] == j1
    finally:
        gate.set()
    _wait_status(client, j1, "done")


# ── validation + save ─────────────────────────────────────────────────────────

def test_search_no_keywords_400(client, monkeypatch):
    import search.cli as cli
    monkeypatch.setattr(cli, "load_user_config", lambda path=None: {})
    resp = client.post("/api/search", headers=_H, json={})
    assert resp.status_code == 400
    assert "keyword" in resp.get_json()["error"]


def test_search_save_persists_defaults(client, monkeypatch):
    """save:true writes keywords/location/salary to the project config exactly as
    the tk Save button does, before the job runs."""
    saved = {}
    monkeypatch.setattr(workspace, "load_config", lambda slug=None: {})
    monkeypatch.setattr(workspace, "save_config",
                        lambda cfg, slug=None: saved.update(cfg))
    monkeypatch.setattr("search.search_job.run_search", lambda *a, **k: ([], []))
    monkeypatch.setattr("search.search_job.seen_for_urls", lambda urls: set())

    jid = client.post("/api/search", headers=_H,
                      json={"keywords": ["nurse", "rn"], "location": "Boston",
                            "min_salary": 90000, "save": True}).get_json()["job_id"]
    _wait_status(client, jid, "done")
    assert saved["keywords"] == ["nurse", "rn"]
    assert saved["location"] == "Boston"
    assert saved["salary_min"] == 90000


# ── mutating routes: 403 without origin ───────────────────────────────────────

@pytest.mark.parametrize("path,body", [
    ("/api/search", {"keywords": ["x"]}),
    ("/api/search/track", {"row": {"url": "u"}}),
    ("/api/search/dismiss", {"url": "u"}),
    ("/api/search/add-all", {"rows": [{"url": "u"}]}),
])
def test_search_routes_headerless_403(client, path, body):
    assert client.post(path, json=body).status_code == 403


# ── track / dismiss / add-all parity ──────────────────────────────────────────

def test_track_wraps_single_row_in_list(client, tmp_db, monkeypatch):
    """/search/track calls track_search_results with a ONE-element list (the
    service takes a list) and returns its (added, skipped) counts."""
    calls = {}
    from tracker import service

    def fake_track(jobs, seen=None):
        calls["n"] = len(jobs)
        calls["title"] = jobs[0].title
        return (1, 0)
    monkeypatch.setattr(service, "track_search_results", fake_track)

    row = {"title": "Sr Eng", "company": "Acme", "url": "https://x/1",
           "score": 80, "source_api": "adzuna"}
    resp = client.post("/api/search/track", headers=_H, json={"row": row})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "added": 1, "skipped": 0}
    assert calls["n"] == 1 and calls["title"] == "Sr Eng"


def test_track_missing_row_400(client):
    assert client.post("/api/search/track", headers=_H,
                       json={"row": {}}).status_code == 400


def test_dismiss_takes_url_only(client, monkeypatch):
    from tracker import service
    seen = {}
    monkeypatch.setattr(service, "dismiss_url",
                        lambda url: seen.update(url=url))
    resp = client.post("/api/search/dismiss", headers=_H,
                       json={"url": "https://x/9"})
    assert resp.get_json() == {"ok": True}
    assert seen["url"] == "https://x/9"


def test_dismiss_missing_url_400(client):
    assert client.post("/api/search/dismiss", headers=_H,
                       json={}).status_code == 400


def test_add_all_uses_per_company_cap(client, monkeypatch):
    """/search/add-all calls inbox_add_many with per_company_cap from the project's
    max_per_company (tk parity: per_company_cap only, no new_batch) and pins the
    active project across the write."""
    captured = {}
    import tracker.db as db

    def fake_add_many(jobs, per_company_cap=0, new_batch="", overflow_out=None):
        captured["n"] = len(jobs)
        captured["cap"] = per_company_cap
        captured["new_batch"] = new_batch
        return len(jobs)
    monkeypatch.setattr(db, "inbox_add_many", fake_add_many)

    pins = []
    monkeypatch.setattr(workspace, "pin_active", lambda s: pins.append(("pin", s)))
    monkeypatch.setattr(workspace, "unpin_active", lambda: pins.append(("unpin",)))

    rows = [{"title": "A", "company": "Acme", "url": "https://x/1"},
            {"title": "B", "company": "Acme", "url": "https://x/2"}]
    resp = client.post("/api/search/add-all", headers=_H, json={"rows": rows})
    assert resp.get_json() == {"ok": True, "added": 2}
    assert captured["n"] == 2
    assert captured["cap"] == 15          # from stubbed max_per_company
    assert captured["new_batch"] == ""    # tk never passes new_batch here
    assert pins == [("pin", "projA"), ("unpin",)]  # pinned before, unpinned after


def test_add_all_empty_400(client):
    assert client.post("/api/search/add-all", headers=_H,
                       json={"rows": []}).status_code == 400
