"""JobRunner lifecycle + SSE framing.

Unit-tests the runner directly (start -> lines -> done, failure capture, 409
single-flight, independent keys, per-run global reset) and exercises the SSE
endpoint through the private /api/_test/job hook (TESTING-only).
"""
import threading

import pytest

from tests.webui.conftest import wait_until
from webui.jobs import JobRunner, JobConflict


def _wait_status(runner, job_id, target, timeout=3.0):
    def _check():
        snap = runner.status(job_id)
        return snap if snap and snap["status"] == target else None
    return wait_until(
        _check, timeout=timeout,
        message=f"job {job_id} never reached {target}: {runner.status(job_id)}")


def _terminal_snap(client, job_id, target):
    """Route-level poll predicate: the /api/jobs/<id> snapshot once its status
    matches ``target``, or None (keep polling)."""
    snap = client.get(f"/api/jobs/{job_id}").get_json()
    return snap if snap.get("status") == target else None


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


def test_finished_job_releases_its_cached_db_connection(tmp_db):
    # An engine job opens a per-thread WAL connection via tracker.db.get_conn();
    # before the S40 fix that handle was reclaimed only lazily on the NEXT
    # new-thread cache miss, so tracker.db could stay locked ([WinError 32])
    # through a project-folder delete after a first_run job. JobRunner._run's
    # finally now closes the CURRENT thread's connection, so the registry holds
    # no live connection for the (dead) job thread WITHOUT a fresh-thread sweep.
    from tracker import db

    runner = JobRunner()
    captured = {}

    def fn(h):
        # Touch get_conn on the job thread exactly like init_db/inbox_add_many do.
        db.get_conn().execute("PRAGMA user_version")
        captured["ident"] = threading.get_ident()
        return "ok"

    jid = runner.start("first_run", "k1", fn, exclusive=True)
    _wait_status(runner, jid, "done")
    # Give the daemon thread a beat to run its finally after finish() flips status.
    wait_until(
        lambda: True if captured.get("ident") not in db._registry else None,
        timeout=3.0,
        message="job thread's cached connection was never released from _registry")

    job_ident = captured["ident"]
    # The finally released it WITHOUT needing a new-thread get_conn() sweep: the
    # registry entry for the (now-dead) job thread ident is simply gone.
    assert job_ident not in db._registry


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
        # Poll for cancellation cooperatively (a short interval since this runs
        # in the runner's own background thread, not the test's poll-and-assert
        # path -- h.cancelled is a threading.Event, so .wait() blocks without a
        # busy-loop and returns as soon as .set() is called elsewhere).
        h.cancelled.wait(2.0)
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
    snap = wait_until(
        lambda: _terminal_snap(client, jid, "done"),
        message=f"job {jid} never reached done")
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
    wait_until(lambda: _terminal_snap(client, j1, "done"),
              message=f"job {j1} never reached done")
    assert client.get(f"/api/jobs/{j1}").get_json()["status"] == "done"


def test_sse_streams_line_and_done_frames(client):
    resp = _start_test_job(client, kind="sse", key="a", lines=["L1", "L2", "L3"])
    jid = resp.get_json()["job_id"]
    # Let it finish so the replay buffer holds all lines and the stream closes.
    wait_until(lambda: _terminal_snap(client, jid, "done"),
              message=f"job {jid} never reached done")

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
    wait_until(lambda: _terminal_snap(client, jid, "failed"),
              message=f"job {jid} never reached failed")
    text = client.get(f"/api/jobs/{jid}/events").get_data(as_text=True)
    assert "event: line\ndata: boom-line" in text
    assert "event: error" in text
    assert "RuntimeError" in text


def test_sse_unknown_job_404(client):
    resp = client.get("/api/jobs/nope/events")
    assert resp.status_code == 404


# ── finished-job eviction (memory-leak guard) ─────────────────────────────────
import webui.jobs as _jobs_mod


def test_old_finished_job_evicted_on_next_start():
    runner = JobRunner()
    jid = runner.start("k", "old", lambda h: "r")
    _wait_status(runner, jid, "done")
    # Backdate finished_at past the TTL so it becomes eviction-eligible.
    runner._jobs[jid].finished_at -= (_jobs_mod._FINISHED_TTL_SECS + 1)
    # Starting a new job triggers the eviction sweep.
    runner.start("k", "new-gate", lambda h: "r2")
    assert runner.status(jid) is None  # evicted -> unknown-id contract (404)


def test_running_job_is_never_evicted():
    runner = JobRunner()
    gate = threading.Event()
    jid = runner.start("k", "running", lambda h: gate.wait(2.0))
    # Force the age check to (falsely) look ancient if it were terminal — but
    # the job is still running (finished_at is None), so eviction must skip it
    # regardless of how many other jobs get started afterward.
    for i in range(5):
        runner.start("k", f"filler-{i}", lambda h: "r")
    assert runner.status(jid)["status"] == "running"
    gate.set()
    _wait_status(runner, jid, "done")


def test_subscribed_finished_job_never_evicted():
    runner = JobRunner()
    jid = runner.start("k", "subbed", lambda h: "r")
    _wait_status(runner, jid, "done")
    q = runner.subscribe(jid)  # live subscriber still attached
    try:
        runner._jobs[jid].finished_at -= (_jobs_mod._FINISHED_TTL_SECS + 1)
        runner.start("k", "trigger", lambda h: "r2")
        # Still present -- a subscriber is attached, so eviction must skip it.
        assert runner.status(jid) is not None
    finally:
        runner.unsubscribe(jid, q)


def test_cap_enforcement_evicts_oldest_finished_first():
    """The cap is enforced AT start()-time (inside the existing lock, per the
    task's design), not continuously: each start() sweeps *existing* finished
    jobs down to the cap BEFORE registering the new (initially running) job.
    So the steady-state invariant is <= cap+1 total finished (the cap itself,
    plus whichever just-registered job has since completed) — never allowed to
    grow further from there, and the OLDEST finished jobs are always the ones
    evicted first.
    """
    runner = JobRunner()
    cap = _jobs_mod._FINISHED_CAP
    ids = []
    for i in range(cap + 10):
        jid = runner.start("k", f"cap-{i}", lambda h: "r")
        _wait_status(runner, jid, "done")
        ids.append(jid)
        finished_count = sum(1 for j in runner._jobs.values()
                             if j.finished_at is not None)
        assert finished_count <= cap + 1
    # The OLDEST finished jobs (earliest in `ids`) must be the ones gone.
    assert runner.status(ids[0]) is None
    assert runner.status(ids[-1]) is not None
