"""POST /api/runs/daily run-shaping knobs (S36 parity gap P1): optional
``max_pages``/``min_score`` body fields thread through to daily_run's
``--max-pages``/``--min-score`` argv flags; absent knobs keep the legacy call
shape (and argv) exactly; malformed values are a 400 envelope, never clamped.
"""
import sys
import time
import types

import pytest

import applog
import workspace
from webui.api import runs as runs_mod
from webui.jobs import runner


_H = {"Origin": "http://127.0.0.1:5002"}


@pytest.fixture(autouse=True)
def _no_last_run(monkeypatch):
    """Default every knobs test to the FIRST-run state (no last_run.json). The
    first-run default only fires when max_pages is unset, so the existing
    explicit-knob tests are unaffected; the subsequent-run tests below opt back
    into a present last_run.json."""
    monkeypatch.setattr(applog, "last_run_info", lambda slug=None: None)


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
    monkeypatch.setattr(workspace, "registry_active_slug", lambda: "projA")
    monkeypatch.setattr(workspace, "active_slug", lambda: "projA")


def _wait_done(client, job_id, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = client.get(f"/api/jobs/{job_id}").get_json()
        if snap.get("status") in ("done", "failed"):
            return snap
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never finished")


# ── route -> ingest pass-through ──────────────────────────────────────────────

def test_knobs_forwarded_to_ingest(client, monkeypatch):
    seen = {}

    def fake_ingest(slug, *, on_line=None, cancel=None, max_pages=None,
                    min_score=None):
        seen.update(slug=slug, max_pages=max_pages, min_score=min_score)
        return 0

    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)
    resp = client.post("/api/runs/daily", headers=_H,
                       json={"max_pages": 1, "min_score": 55})
    assert resp.status_code == 200
    _wait_done(client, resp.get_json()["job_id"])
    assert seen == {"slug": "projA", "max_pages": 1, "min_score": 55}


def test_absent_knobs_keep_legacy_call_shape(client, monkeypatch):
    # A knob-less POST on a SUBSEQUENT run (last_run.json present) must call the
    # ingest WITHOUT the knob kwargs at all — the pre-P1 call shape (existing
    # fakes/wrappers with the old signature keep working, and the argv stays
    # byte-identical). (First-run quick-pass is covered separately below.)
    monkeypatch.setattr(applog, "last_run_info",
                        lambda slug=None: {"added": 5})

    def fake_ingest(slug, *, on_line=None, cancel=None):
        return 0

    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)
    resp = client.post("/api/runs/daily", headers=_H)
    assert resp.status_code == 200
    snap = _wait_done(client, resp.get_json()["job_id"])
    assert snap["status"] == "done"


@pytest.mark.parametrize("body,msg", [
    ({"max_pages": 0}, "max_pages must be between 1 and 10"),
    ({"max_pages": 11}, "max_pages must be between 1 and 10"),
    ({"max_pages": "lots"}, "max_pages must be an integer"),
    ({"max_pages": 1.5}, "max_pages must be an integer"),
    ({"max_pages": True}, "max_pages must be an integer"),
    ({"min_score": -1}, "min_score must be between 0 and 100"),
    ({"min_score": 101}, "min_score must be between 0 and 100"),
    ({"min_score": "high"}, "min_score must be an integer"),
])
def test_bad_knobs_are_400_never_clamped(client, monkeypatch, body, msg):
    def boom(*a, **k):  # the ingest must never start on a bad request
        raise AssertionError("ingest started despite invalid knobs")

    monkeypatch.setattr(runs_mod, "_daily_ingest", boom)
    resp = client.post("/api/runs/daily", headers=_H, json=body)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False and data["error"] == msg


def test_numeric_string_knob_accepted(client, monkeypatch):
    # JSON from hand-rolled clients often stringifies ints; "3" is unambiguous.
    seen = {}

    def fake_ingest(slug, *, on_line=None, cancel=None, max_pages=None,
                    min_score=None):
        seen.update(max_pages=max_pages)
        return 0

    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)
    resp = client.post("/api/runs/daily", headers=_H, json={"max_pages": "3"})
    assert resp.status_code == 200
    _wait_done(client, resp.get_json()["job_id"])
    assert seen == {"max_pages": 3}


# ── first-run quick pass (B1) ─────────────────────────────────────────────────

def test_first_run_defaults_max_pages_1(client, monkeypatch):
    # No last_run.json => first run: a knob-less POST defaults max_pages=1 and
    # forwards it to the ingest (so a new user gets a fast first pass).
    monkeypatch.setattr(applog, "last_run_info", lambda slug=None: None)
    seen = {}

    def fake_ingest(slug, *, on_line=None, cancel=None, max_pages=None,
                    min_score=None):
        seen.update(slug=slug, max_pages=max_pages, min_score=min_score)
        return 0

    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)
    resp = client.post("/api/runs/daily", headers=_H)
    assert resp.status_code == 200
    _wait_done(client, resp.get_json()["job_id"])
    assert seen == {"slug": "projA", "max_pages": 1, "min_score": None}


def test_first_run_emits_quick_pass_log_line(client, monkeypatch):
    # The first-run quick pass announces itself in the job console.
    monkeypatch.setattr(applog, "last_run_info", lambda slug=None: None)

    def fake_ingest(slug, *, on_line=None, cancel=None, max_pages=None,
                    min_score=None):
        return 0

    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)
    resp = client.post("/api/runs/daily", headers=_H)
    assert resp.status_code == 200
    snap = _wait_done(client, resp.get_json()["job_id"])
    lines = " ".join(snap.get("lines_tail") or [])
    assert "First run: quick pass" in lines


def test_body_max_pages_overrides_first_run_default(client, monkeypatch):
    # A body-explicit max_pages ALWAYS wins, even on a first run.
    monkeypatch.setattr(applog, "last_run_info", lambda slug=None: None)
    seen = {}

    def fake_ingest(slug, *, on_line=None, cancel=None, max_pages=None,
                    min_score=None):
        seen.update(max_pages=max_pages)
        return 0

    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)
    resp = client.post("/api/runs/daily", headers=_H, json={"max_pages": 5})
    assert resp.status_code == 200
    snap = _wait_done(client, resp.get_json()["job_id"])
    assert seen == {"max_pages": 5}
    # No quick-pass line when the user set the depth themselves.
    lines = " ".join(snap.get("lines_tail") or [])
    assert "First run: quick pass" not in lines


def test_subsequent_run_keeps_engine_defaults(client, monkeypatch):
    # last_run.json present => NOT a first run: a knob-less POST forwards NO knobs
    # (engine defaults), and emits no quick-pass line.
    monkeypatch.setattr(applog, "last_run_info",
                        lambda slug=None: {"added": 3})

    def fake_ingest(slug, *, on_line=None, cancel=None):
        return 0

    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)
    resp = client.post("/api/runs/daily", headers=_H)
    assert resp.status_code == 200
    snap = _wait_done(client, resp.get_json()["job_id"])
    assert snap["status"] == "done"
    lines = " ".join(snap.get("lines_tail") or [])
    assert "First run: quick pass" not in lines


# ── daily_run_core argv threading (real run_ingest, stubbed daily_run) ────────

def _stub_daily_run(monkeypatch, captured):
    fake = types.ModuleType("daily_run")

    def run_main():
        captured["argv"] = list(sys.argv)
        return 0

    fake.run_main = run_main
    monkeypatch.setitem(sys.modules, "daily_run", fake)


def test_run_ingest_threads_knobs_into_argv(monkeypatch):
    import daily_run_core
    captured = {}
    _stub_daily_run(monkeypatch, captured)
    rc = daily_run_core.run_ingest("projA", max_pages=1, min_score=60)
    assert rc == 0
    assert captured["argv"] == ["daily_run.py", "--project", "projA",
                                "--max-pages", "1", "--min-score", "60"]


def test_run_ingest_default_argv_unchanged(monkeypatch):
    import daily_run_core
    captured = {}
    _stub_daily_run(monkeypatch, captured)
    assert daily_run_core.run_ingest("projA") == 0
    assert captured["argv"] == ["daily_run.py", "--project", "projA"]
