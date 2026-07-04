"""In-process background job runner for long engine operations (daily run,
search, list-building) with per-``(kind, key)`` single-flight locking and SSE
log fan-out.

Design contract (binding, from the migration plan):

* One process = the app. Engine jobs must NEVER run two at once in-process —
  ``applog._WARNED_ONCE`` and ``discoverer._RUN_QUERY_MEMO`` are per-run PROCESS
  globals, and ``rescore``/DB writers assume serial access. The single-flight
  lock keyed on ``(kind, key)`` (``key`` = the project slug for project-touching
  jobs) is what makes the per-run global RESET below safe: no second job of the
  same kind+key can start and clobber the memo mid-run.
* Before invoking the job fn we mirror ``daily_run.main()``'s per-run resets:
  ``applog.reset_run_warnings()`` + ``discoverer.reset_run_memo()`` (late,
  defensive imports — a job kind that doesn't touch the engine still gets a clean
  slate, and a missing module never breaks the runner).
* Progress streams over SSE: each job owns a bounded log ``deque`` (replayable
  tail) AND a set of subscriber ``queue.Queue``s the ``JobHandle.log`` call
  fans out to live. Terminal state (``done``/``failed``) is pushed as a sentinel
  so a draining SSE generator knows to close.

No third-party deps — stdlib ``threading`` / ``queue`` / ``collections.deque``.
"""
from __future__ import annotations

import threading
import queue
import uuid
from collections import deque
from typing import Any, Callable, Optional


# How many log lines each job retains for replay (the SSE ``lines_tail`` and
# ``status`` snapshot). Bounded so a chatty run can't grow memory unbounded.
_LOG_MAXLEN = 2000
# How many lines ``status`` returns as the "tail".
_STATUS_TAIL = 50
# Sentinel pushed onto every subscriber queue when a job reaches a terminal
# state, so an SSE drain loop unblocks and emits its done/error frame.
_DONE = object()


class JobConflict(Exception):
    """Raised by :meth:`JobRunner.start` when a job with the same ``(kind, key)``
    is still running. Carries the id of the in-flight job so the route can answer
    409 ``{ok:false, error:"already running", job_id: <running>}``."""

    def __init__(self, running_job_id: str):
        super().__init__(f"a {running_job_id} job is already running")
        self.running_job_id = running_job_id


class JobHandle:
    """The per-job surface passed to a job fn: a ``log(line)`` sink and a
    ``cancelled`` event. The fn should poll ``self.cancelled.is_set()`` at safe
    points to support cooperative cancellation (wired in later phases)."""

    def __init__(self, job: "_Job"):
        self._job = job
        self.cancelled = job.cancel_event

    def log(self, line: str) -> None:
        """Append a log line to the job's bounded buffer AND fan it out live to
        every subscribed SSE queue. Thread-safe."""
        self._job.append_line(str(line))


class _Job:
    """Internal per-job state. ``status`` transitions running -> done|failed|
    cancelled; ``lines`` is the bounded replay buffer; ``subscribers`` are live
    SSE queues."""

    def __init__(self, job_id: str, kind: str, key: str):
        self.id = job_id
        self.kind = kind
        self.key = key
        self.status = "running"
        self.result: Any = None
        self.error: Optional[str] = None
        self.lines: deque[str] = deque(maxlen=_LOG_MAXLEN)
        self.cancel_event = threading.Event()
        self._subscribers: set[queue.Queue] = set()
        self._lock = threading.Lock()

    # ── log fan-out ────────────────────────────────────────────────────────────
    def append_line(self, line: str) -> None:
        with self._lock:
            self.lines.append(line)
            subs = list(self._subscribers)
        # Fan out outside the lock so a slow/full subscriber can't block loggers.
        for q in subs:
            try:
                q.put_nowait(("line", line))
            except queue.Full:
                pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=10000)
        with self._lock:
            self._subscribers.add(q)
            terminal = self.status != "running"
        # A subscriber that arrives AFTER the job already finished must still get
        # a terminal sentinel, or its SSE drain would block forever.
        if terminal:
            try:
                q.put_nowait(_DONE)
            except queue.Full:
                pass
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def finish(self, status: str, result: Any, error: Optional[str]) -> None:
        with self._lock:
            self.status = status
            self.result = result
            self.error = error
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(_DONE)
            except queue.Full:
                pass

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "lines_tail": list(self.lines)[-_STATUS_TAIL:],
                "result": self.result,
                "error": self.error,
            }


class JobRunner:
    """Registry + launcher for background jobs. Thread-safe; a module-level
    :data:`runner` singleton is the app-wide instance."""

    def __init__(self):
        self._jobs: dict[str, _Job] = {}
        self._active: dict[tuple[str, str], str] = {}  # (kind, key) -> job_id
        self._lock = threading.Lock()

    def start(self, kind: str, key: str, fn: Callable[[JobHandle], Any]) -> str:
        """Launch ``fn(handle)`` on a daemon thread; return the new job id.

        Single-flight: if a job with the same ``(kind, key)`` is still running,
        raise :class:`JobConflict` carrying that job's id (route -> 409). This is
        the serialization guarantee that makes the per-run engine-global reset
        below safe.
        """
        gate = (str(kind), str(key))
        job_id = uuid.uuid4().hex
        with self._lock:
            running = self._active.get(gate)
            if running is not None and running in self._jobs \
                    and self._jobs[running].status == "running":
                raise JobConflict(running)
            job = _Job(job_id, str(kind), str(key))
            self._jobs[job_id] = job
            self._active[gate] = job_id

        handle = JobHandle(job)

        def _run():
            # Per-run process globals — reset EXACTLY like daily_run.main() does,
            # so a GUI/web 'Update now' doesn't carry a previous run's warn-once
            # set or query memo. Late + defensive imports: a job that never
            # touches the engine still starts clean, and an absent module (or a
            # partial checkout) never breaks the runner.
            try:
                import applog
                applog.reset_run_warnings()
            except ImportError:
                pass
            try:
                from scrape import discoverer
                discoverer.reset_run_memo()
            except ImportError:
                pass
            try:
                result = fn(handle)
            except Exception as exc:  # noqa: BLE001 — capture ANY failure for status
                job.finish("failed", None, f"{type(exc).__name__}: {exc}")
                return
            status = "cancelled" if job.cancel_event.is_set() else "done"
            job.finish(status, result, None)

        t = threading.Thread(target=_run, name=f"job-{kind}-{job_id[:8]}",
                             daemon=True)
        t.start()
        return job_id

    def cancel(self, job_id: str) -> bool:
        """Signal cooperative cancellation for a running job. Returns True if the
        job exists and was running (the fn must poll ``handle.cancelled``)."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.status != "running":
            return False
        job.cancel_event.set()
        return True

    def status(self, job_id: str) -> Optional[dict]:
        """Snapshot of a job: ``{status, lines_tail (<=50), result, error}``, or
        None if the id is unknown (route -> 404)."""
        with self._lock:
            job = self._jobs.get(job_id)
        return job.snapshot() if job is not None else None

    def subscribe(self, job_id: str) -> Optional[queue.Queue]:
        """A live log queue for a job (SSE). None if the id is unknown. If the
        job already finished, the queue is pre-seeded with the terminal sentinel
        so the drain loop closes immediately after replaying the tail."""
        with self._lock:
            job = self._jobs.get(job_id)
        return job.subscribe() if job is not None else None

    def unsubscribe(self, job_id: str, q: queue.Queue) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            job.unsubscribe(q)

    def _get(self, job_id: str) -> Optional[_Job]:
        """Internal: the raw job object (used by the SSE route to read the replay
        tail before draining). Not part of the public status contract."""
        with self._lock:
            return self._jobs.get(job_id)


# App-wide singleton (one process = the app).
runner = JobRunner()

# Sentinel exported for the SSE route's drain loop.
DONE = _DONE
