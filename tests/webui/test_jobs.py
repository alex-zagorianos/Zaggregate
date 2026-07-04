"""JobRunner lifecycle + SSE framing.

Unit-tests the runner directly (start -> lines -> done, failure capture, 409
single-flight, independent keys, per-run global reset) and exercises the SSE
endpoint through the private /api/_test/job hook (TESTING-only).
"""
import threading
import time

import pytest

from webui.jobs import JobRunner, JobConflict


def _wait_status(runner, job_id, target, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = runner.status(job_id)
        if snap and snap["status"] == target:
            return snap
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never reached {target}: "
                         f"{runner.status(job_id)}")


# ── direct runner lifecycle ───────────────────────────────────────────────────

def test_start_lines_done():
    runner = JobRunner()

    def fn(h):
        h.log("alpha")
        h.log("beta")
        return {"value": 42}

    jid = runner.start("test", "k1", fn)
    snap = _wait_status(runner, jid, "done")
    assert snap["result"] == {"value": 42}
    assert snap["error"] is None
    assert snap["lines_tail"] == ["alpha", "beta"]


def test_failure_capture():
    runner = JobRunner()

    def fn(h):
        h.log("before boom")
        raise ValueError("kaboom")

    jid = runner.start("test", "k1", fn)
    snap = _wait_status(runner, jid, "failed")
    assert snap["result"] is None
    assert "kaboom" in snap["error"]
    assert snap["error"].startswith("ValueError")
    assert snap["lines_tail"] == ["before boom"]


def test_single_flight_conflict_same_kind_key():
    runner = JobRunner()
    gate = threading.Event()

    def blocker(h):
        gate.wait(2.0)
        return "ok"

    jid = runner.start("daily", "projA", blocker)
    # A second job with the SAME (kind, key) while the first still runs -> 409.
    with pytest.raises(JobConflict) as ei:
        runner.start("daily", "projA", lambda h: None)
    assert ei.value.running_job_id == jid
    gate.set()
    _wait_status(runner, jid, "done")


def test_independent_keys_do_not_conflict():
    runner = JobRunner()
    gate = threading.Event()

    def blocker(h):
        gate.wait(2.0)
        return "ok"

    j1 = runner.start("daily", "projA", blocker)
    # Different key -> allowed concurrently.
    j2 = runner.start("daily", "projB", blocker)
    # Different kind, same key -> also allowed.
    j3 = runner.start("search", "projA", blocker)
    assert len({j1, j2, j3}) == 3
    gate.set()
    for jid in (j1, j2, j3):
        _wait_status(runner, jid, "done")


def test_same_gate_reusable_after_completion():
    runner = JobRunner()
    j1 = runner.start("daily", "projA", lambda h: "first")
    _wait_status(runner, j1, "done")
    # Once the first finished, the gate is free again.
    j2 = runner.start("daily", "projA", lambda h: "second")
    _wait_status(runner, j2, "done")
    assert j1 != j2


def test_status_unknown_job_is_none():
    runner = JobRunner()
    assert runner.status("nope") is None


def test_cancel_sets_event_and_marks_cancelled():
    runner = JobRunner()
    started = threading.Event()
    proceed = threading.Event()

    def fn(h):
        started.set()
        # Poll for cancellation cooperatively.
        for _ in range(200):
            if h.cancelled.is_set():
                break
            time.sleep(0.01)
        proceed.set()
        return "done"

    jid = runner.start("daily", "projC", fn)
    assert started.wait(2.0)
    assert runner.cancel(jid) is True
    assert proceed.wait(2.0)
    _wait_status(runner, jid, "cancelled")


def test_reset_hooks_called_before_fn():
    """The runner must reset applog warn-once + discoverer memo before fn runs
    (mirrors daily_run.main). We seed both process globals and assert the job saw
    them cleared."""
    import applog
    from scrape import discoverer
    runner = JobRunner()
    applog._WARNED_ONCE.add("stale")
    discoverer._RUN_QUERY_MEMO[("q", "loc")] = {"x": 1}

    seen = {}

    def fn(h):
        seen["warned"] = set(applog._WARNED_ONCE)
        seen["memo"] = dict(discoverer._RUN_QUERY_MEMO)
        return None

    jid = runner.start("daily", "reset", fn)
    _wait_status(runner, jid, "done")
    assert seen["warned"] == set()
    assert seen["memo"] == {}


# ── SSE endpoint framing (via the TESTING-only test hook) ──────────────────────

def _start_test_job(client, **body):
    resp = client.post("/api/_test/job", json=body)
    return resp


def test_test_hook_starts_job_and_status(client):
    resp = _start_test_job(client, kind="t", key="a", lines=["x", "y"])
    assert resp.status_code == 200
    jid = resp.get_json()["job_id"]
    # Poll the public status route to terminal.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        snap = client.get(f"/api/jobs/{jid}").get_json()
        if snap["status"] == "done":
            break
        time.sleep(0.01)
    assert snap["ok"] is True
    assert snap["status"] == "done"
    assert snap["result"] == {"count": 2}
    assert snap["lines_tail"] == ["x", "y"]


def test_job_status_unknown_404(client):
    resp = client.get("/api/jobs/deadbeef")
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_test_hook_409_single_flight(client):
    # Deterministic: the first job BLOCKS on a hold token until released, so the
    # second POST on the same (kind,key) is guaranteed to hit the running window.
    token = "hold-409"
    r1 = _start_test_job(client, kind="dupe", key="same", lines=["a"], hold=token)
    assert r1.status_code == 200
    j1 = r1.get_json()["job_id"]
    try:
        r2 = _start_test_job(client, kind="dupe", key="same", lines=["z"])
        assert r2.status_code == 409
        body = r2.get_json()
        assert body["ok"] is False
        assert body["error"] == "already running"
        assert body["job_id"] == j1
    finally:
        client.post(f"/api/_test/release/{token}")
    # After release the first job completes and the gate frees.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if client.get(f"/api/jobs/{j1}").get_json()["status"] == "done":
            break
        time.sleep(0.01)
    assert client.get(f"/api/jobs/{j1}").get_json()["status"] == "done"


def test_sse_streams_line_and_done_frames(client):
    resp = _start_test_job(client, kind="sse", key="a", lines=["L1", "L2", "L3"])
    jid = resp.get_json()["job_id"]
    # Let it finish so the replay buffer holds all lines and the stream closes.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if client.get(f"/api/jobs/{jid}").get_json()["status"] == "done":
            break
        time.sleep(0.01)

    stream = client.get(f"/api/jobs/{jid}/events")
    assert stream.status_code == 200
    assert stream.mimetype == "text/event-stream"
    text = stream.get_data(as_text=True)
    assert "retry: 2000" in text
    assert "event: line\ndata: L1" in text
    assert "event: line\ndata: L2" in text
    assert "event: line\ndata: L3" in text
    assert "event: done" in text
    # The done frame carries the JSON result.
    assert '"count": 3' in text


def test_sse_error_frame_on_failure(client):
    resp = _start_test_job(client, kind="sse", key="fail", lines=["boom-line"],
                           fail=True)
    jid = resp.get_json()["job_id"]
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if client.get(f"/api/jobs/{jid}").get_json()["status"] == "failed":
            break
        time.sleep(0.01)
    text = client.get(f"/api/jobs/{jid}/events").get_data(as_text=True)
    assert "event: line\ndata: boom-line" in text
    assert "event: error" in text
    assert "RuntimeError" in text


def test_sse_unknown_job_404(client):
    resp = client.get("/api/jobs/nope/events")
    assert resp.status_code == 404
