"""POST /api/runs/daily — job lifecycle, SSE lines, single-flight 409,
cross-project exclusive mutex, cancel, and the pin/unpin contract.

The extracted ingest fn (``webui.api.runs._daily_ingest``) is monkeypatched with a
fake for the lifecycle/conflict tests (deterministic, no engine). The pin/unpin
test uses the REAL ``daily_run_core.run_ingest`` with a stubbed ``daily_run``
module so the S27-safe pin path is verified end-to-end through the route.
"""
import sys
import time
import types

import pytest

import workspace
from webui.api import runs as runs_mod
from webui.jobs import runner


_LOOPBACK = "http://127.0.0.1:5002"
_H = {"Origin": _LOOPBACK}


@pytest.fixture(autouse=True)
def _reset_runner():
    """The app-wide runner singleton is shared across tests; clear its registries
    (and the exclusive slot) around each test so a blocked/held daily job can't
    leak the mutex into an unrelated test."""
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
    """Pin a deterministic active project so ``runs/daily`` keys the job on a known
    slug (and so the pin/unpin assertions have a concrete value)."""
    monkeypatch.setattr(workspace, "active_slug", lambda: "projA")


def _wait_status(client, job_id, target, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = client.get(f"/api/jobs/{job_id}").get_json()
        if snap.get("status") == target:
            return snap
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never reached {target}: "
                         f"{client.get(f'/api/jobs/{job_id}').get_json()}")


# ── happy-path lifecycle + SSE ────────────────────────────────────────────────

def test_daily_run_lifecycle_and_lines(client, monkeypatch):
    def fake_ingest(slug, *, on_line=None, cancel=None):
        assert slug == "projA"
        on_line("[Adzuna] 12 results")
        on_line("inbox: added 3")
        return 0
    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)

    resp = client.post("/api/runs/daily", headers=_H)
    assert resp.status_code == 200
    jid = resp.get_json()["job_id"]
    snap = _wait_status(client, jid, "done")
    assert snap["result"] == {"rc": 0, "slug": "projA"}
    assert snap["lines_tail"] == ["[Adzuna] 12 results", "inbox: added 3"]


def test_daily_run_sse_streams_lines(client, monkeypatch):
    def fake_ingest(slug, *, on_line=None, cancel=None):
        on_line("L1")
        on_line("L2")
        return 0
    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)

    jid = client.post("/api/runs/daily", headers=_H).get_json()["job_id"]
    _wait_status(client, jid, "done")
    text = client.get(f"/api/jobs/{jid}/events").get_data(as_text=True)
    assert "event: line\ndata: L1" in text
    assert "event: line\ndata: L2" in text
    assert "event: done" in text


def test_daily_run_headerless_403(client, monkeypatch):
    monkeypatch.setattr(runs_mod, "_daily_ingest",
                        lambda slug, **k: 0)
    resp = client.post("/api/runs/daily")   # no Origin/Referer
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}


# ── single-flight 409 (same project) ──────────────────────────────────────────

def test_daily_run_409_same_project(client, monkeypatch):
    import threading
    gate = threading.Event()

    def blocking_ingest(slug, *, on_line=None, cancel=None):
        gate.wait(3.0)
        return 0
    monkeypatch.setattr(runs_mod, "_daily_ingest", blocking_ingest)

    r1 = client.post("/api/runs/daily", headers=_H)
    j1 = r1.get_json()["job_id"]
    try:
        r2 = client.post("/api/runs/daily", headers=_H)   # same active project
        assert r2.status_code == 409
        body = r2.get_json()
        assert body["ok"] is False
        assert body["error"] == "already running"
        assert body["job_id"] == j1
    finally:
        gate.set()
    _wait_status(client, j1, "done")


# ── cross-project exclusive mutex ─────────────────────────────────────────────

def test_daily_run_exclusive_mutex_across_projects(client, monkeypatch):
    """Project A's daily run in flight must block project B's — the process-wide
    engine mutex (two projects can't ingest concurrently in-process)."""
    import threading
    gate = threading.Event()

    def blocking_ingest(slug, *, on_line=None, cancel=None):
        gate.wait(3.0)
        return 0
    monkeypatch.setattr(runs_mod, "_daily_ingest", blocking_ingest)

    # Start A.
    monkeypatch.setattr(workspace, "active_slug", lambda: "projA")
    r1 = client.post("/api/runs/daily", headers=_H)
    j1 = r1.get_json()["job_id"]
    try:
        # Now B is the active project — a DIFFERENT (kind,key), so single-flight
        # alone would allow it; the exclusive mutex must still 409.
        monkeypatch.setattr(workspace, "active_slug", lambda: "projB")
        r2 = client.post("/api/runs/daily", headers=_H)
        assert r2.status_code == 409
        body = r2.get_json()
        assert body["ok"] is False
        assert body["error"] == "another run is in progress"
        assert body["job_id"] == j1
    finally:
        gate.set()
    _wait_status(client, j1, "done")


def test_exclusive_slot_freed_after_completion(client, monkeypatch):
    """Once A's exclusive job finishes, B may start (the slot is released in the
    runner's finally)."""
    monkeypatch.setattr(runs_mod, "_daily_ingest", lambda slug, **k: 0)
    monkeypatch.setattr(workspace, "active_slug", lambda: "projA")
    j1 = client.post("/api/runs/daily", headers=_H).get_json()["job_id"]
    _wait_status(client, j1, "done")
    monkeypatch.setattr(workspace, "active_slug", lambda: "projB")
    r2 = client.post("/api/runs/daily", headers=_H)
    assert r2.status_code == 200
    _wait_status(client, r2.get_json()["job_id"], "done")


# ── cancel ────────────────────────────────────────────────────────────────────

def test_cancel_job_sets_event(client, monkeypatch):
    import threading
    started = threading.Event()
    saw_cancel = {}

    def ingest(slug, *, on_line=None, cancel=None):
        started.set()
        for _ in range(200):
            if cancel is not None and cancel.is_set():
                saw_cancel["hit"] = True
                break
            time.sleep(0.01)
        return 130
    monkeypatch.setattr(runs_mod, "_daily_ingest", ingest)

    jid = client.post("/api/runs/daily", headers=_H).get_json()["job_id"]
    assert started.wait(2.0)
    resp = client.post(f"/api/jobs/{jid}/cancel", headers=_H)
    assert resp.status_code == 200 and resp.get_json()["cancelled"] is True
    _wait_status(client, jid, "cancelled")
    assert saw_cancel.get("hit") is True


def test_cancel_unknown_job_reports_false(client):
    resp = client.post("/api/jobs/deadbeef/cancel", headers=_H)
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "cancelled": False}


def test_cancel_headerless_403(client):
    assert client.post("/api/jobs/x/cancel").status_code == 403


# ── pin / unpin verified end-to-end through the real core ─────────────────────

def test_daily_run_pins_during_and_unpins_after(client, monkeypatch):
    """Uses the REAL daily_run_core.run_ingest (not the fake ingest), with a
    stubbed daily_run module, to assert the S27-safe pin pattern via
    workspace.pinned(): unpinned before, pinned to the active slug DURING
    run_main, unpinned after. The route resolves the slug via active_slug()
    (patched to 'projA' by the _active_slug fixture); pin_active/unpin_active are
    the real ones."""
    # Belt-and-suspenders: ensure we start from a clean, unpinned state.
    workspace.unpin_active()

    seen = {}
    fake_daily = types.ModuleType("daily_run")

    def fake_run_main():
        seen["pinned_during"] = workspace.pinned()
        return 0
    fake_daily.run_main = fake_run_main
    monkeypatch.setitem(sys.modules, "daily_run", fake_daily)

    assert workspace.pinned() is None            # unpinned before
    jid = client.post("/api/runs/daily", headers=_H).get_json()["job_id"]
    _wait_status(client, jid, "done")
    assert seen["pinned_during"] == "projA"      # pinned to the slug during run
    assert workspace.pinned() is None            # unpinned after (finally)
