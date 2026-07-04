"""Job status + SSE event routes.

Phase 0b ships the READ side of the job surface (status snapshot + live SSE
stream) plus a private test hook to start a fake job through the PUBLIC runner —
no engine job-STARTING routes yet (daily-run wiring is Phase 3). The SSE contract
the frontend consumes:

    retry: 2000\n\n                 (reconnect backoff, once at stream open)
    event: line\ndata: <text>\n\n   (per log line — replayed tail, then live)
    event: done\ndata: <json>\n\n    (terminal success; data = JSON result)
    event: error\ndata: <text>\n\n   (terminal failure; data = error string)

The generator replays the job's buffered lines first (so a late subscriber catches
up), then drains the live subscriber queue until the terminal sentinel arrives.
"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, Response, current_app

from ..jobs import runner, DONE

runs_bp = Blueprint("webui_runs", __name__)


def _sse(event: str, data: str) -> str:
    """One SSE frame. ``data`` is emitted as a single ``data:`` line; callers pass
    already-serialized text (JSON for the done frame)."""
    return f"event: {event}\ndata: {data}\n\n"


@runs_bp.get("/jobs/<job_id>")
def job_status(job_id: str):
    snap = runner.status(job_id)
    if snap is None:
        return jsonify({"ok": False, "error": "unknown job"}), 404
    return jsonify({"ok": True, **snap})


@runs_bp.get("/jobs/<job_id>/events")
def job_events(job_id: str):
    job = runner._get(job_id)
    if job is None:
        return jsonify({"ok": False, "error": "unknown job"}), 404

    def _stream():
        # Reconnect backoff, sent once at stream open.
        yield "retry: 2000\n\n"
        # Snapshot the already-buffered lines and subscribe. Subscribing BEFORE
        # reading the buffer would risk double-emitting a line that lands in the
        # gap; reading first then subscribing risks missing one. We snapshot the
        # buffer length, replay it, then drain live — the runner's per-line
        # fan-out means at worst a boundary line repeats, which an SSE consumer
        # tolerates (idempotent append). Simpler + safe: replay buffer, then live.
        q = runner.subscribe(job_id)
        try:
            for line in list(job.lines):
                yield _sse("line", line)
            if q is not None:
                while True:
                    item = q.get()
                    if item is DONE:
                        break
                    if isinstance(item, tuple) and item and item[0] == "line":
                        yield _sse("line", item[1])
            # Terminal frame from the final status snapshot.
            snap = runner.status(job_id) or {}
            if snap.get("status") == "failed":
                yield _sse("error", str(snap.get("error") or ""))
            else:
                yield _sse("done", json.dumps(snap.get("result")))
        finally:
            if q is not None:
                runner.unsubscribe(job_id, q)

    resp = Response(_stream(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


# ── private test hooks ────────────────────────────────────────────────────────
# No public job-STARTING route exists yet (Phase 3 wires daily-run). Tests need to
# drive the job surface end-to-end through the PUBLIC runner, so these routes are
# registered but gated to TESTING mode at call time. /_test/job starts a job whose
# fn logs the given lines then returns a small result; passing hold=<token> makes
# the fn BLOCK on a server-side event until /_test/release/<token> is called, so a
# test can DETERMINISTICALLY observe a 409 single-flight (no timing race).
import threading as _threading

_HOLD_EVENTS: dict[str, _threading.Event] = {}


def _register_test_hook(bp: Blueprint) -> None:
    from flask import request

    @bp.post("/_test/job")
    def _start_test_job():  # pragma: no cover - registered only under TESTING
        if not current_app.config.get("TESTING"):
            return jsonify({"ok": False, "error": "not found"}), 404
        from ..jobs import JobConflict
        data = request.get_json(force=True, silent=True) or {}
        kind = str(data.get("kind", "test"))
        key = str(data.get("key", "default"))
        lines = data.get("lines") or ["one", "two", "three"]
        fail = bool(data.get("fail"))
        hold = data.get("hold")  # token: block until released (deterministic 409)
        if hold is not None:
            _HOLD_EVENTS.setdefault(str(hold), _threading.Event())

        def _fn(handle):
            for ln in lines:
                handle.log(str(ln))
            if hold is not None:
                _HOLD_EVENTS[str(hold)].wait(5.0)
            if fail:
                raise RuntimeError("boom")
            return {"count": len(lines)}

        try:
            job_id = runner.start(kind, key, _fn)
        except JobConflict as jc:
            return jsonify({"ok": False, "error": "already running",
                            "job_id": jc.running_job_id}), 409
        return jsonify({"ok": True, "job_id": job_id})

    @bp.post("/_test/release/<token>")
    def _release_test_job(token):  # pragma: no cover - registered only under TESTING
        if not current_app.config.get("TESTING"):
            return jsonify({"ok": False, "error": "not found"}), 404
        ev = _HOLD_EVENTS.get(str(token))
        if ev is not None:
            ev.set()
        return jsonify({"ok": True})


_register_test_hook(runs_bp)
