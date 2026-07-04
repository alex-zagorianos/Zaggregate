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
import time
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

# Finished-job retention (memory-leak guard for a long-lived desktop process):
# a job.result can hold a full search row set, so ``_jobs`` must not grow
# unbounded across a session. A terminal job becomes eviction-eligible once it
# is older than ``_FINISHED_TTL_SECS`` AND has no live SSE subscriber still
# attached (evicting out from under an attached client would break replay/​the
# live drain). ``_FINISHED_CAP`` is a hard ceiling on how many finished jobs are
# kept regardless of age, evicting the oldest-finished first (subscriber guard
# still applies) — so a burst of many short-lived jobs can't outgrow memory
# either. Both are enforced opportunistically inside ``start()``'s existing
# lock, not on a timer, so a process that stops starting jobs simply stops
# evicting (acceptable: no jobs -> no growth).
_FINISHED_TTL_SECS = 3600
_FINISHED_CAP = 100


class JobConflict(Exception):
    """Raised by :meth:`JobRunner.start` when a job can't start because another is
    still running. Carries the id of the in-flight job so the route can answer
    409 ``{ok:false, error:"already running", job_id: <running>}``.

    ``same_gate`` distinguishes the two conflict shapes:

    * ``same_gate=True`` — a job with the SAME ``(kind, key)`` is running (e.g. the
      same project's daily run is already in flight). This is the ordinary
      single-flight conflict.
    * ``same_gate=False`` — a DIFFERENT exclusive engine job is running (e.g.
      project A's daily run is in flight and the caller asked to start project B's).
      Blocked by the process-wide exclusive mutex, because the engine's per-run
      process globals (``applog._WARNED_ONCE`` / ``discoverer._RUN_QUERY_MEMO``) and
      the single-active-project assumption make two concurrent in-process ingests
      unsafe REGARDLESS of project.

    Both are 409s carrying the running job's id; the flag lets the route tailor the
    error message ("already running" vs "another run is in progress")."""

    def __init__(self, running_job_id: str, *, same_gate: bool = True):
        super().__init__(f"a {running_job_id} job is already running")
        self.running_job_id = running_job_id
        self.same_gate = same_gate


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
        self.exclusive = False  # set True by JobRunner.start(exclusive=True)
        self.status = "running"
        self.result: Any = None
        self.error: Optional[str] = None
        self.lines: deque[str] = deque(maxlen=_LOG_MAXLEN)
        self.cancel_event = threading.Event()
        self._subscribers: set[queue.Queue] = set()
        self._lock = threading.Lock()
        # Set by finish() (monotonic seconds) -- None while still running. Read
        # by JobRunner._evict_finished to age out old terminal jobs.
        self.finished_at: Optional[float] = None

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

    def has_subscribers(self) -> bool:
        with self._lock:
            return bool(self._subscribers)

    def finish(self, status: str, result: Any, error: Optional[str]) -> None:
        with self._lock:
            self.status = status
            self.result = result
            self.error = error
            self.finished_at = time.monotonic()
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
        # The single in-flight EXCLUSIVE engine job's id, or None. Any exclusive
        # job blocks every OTHER exclusive job process-wide, regardless of
        # (kind, key) — see start(exclusive=True) and the JobConflict docstring.
        self._exclusive_active: Optional[str] = None
        self._lock = threading.Lock()

    def _evict_finished_locked(self) -> None:
        """Prune ``_jobs`` of old/excess terminal jobs. MUST be called with
        ``self._lock`` already held (it mutates ``_jobs``/``_active`` directly,
        the same invariant every other method under this lock relies on).

        Two independent eviction rules, both gated on "no live subscriber still
        attached" (evicting a job an SSE client is actively draining would break
        replay and the live drain — the client would 404 on its next poll):

        1. AGE: any terminal job (done/failed/cancelled) finished more than
           ``_FINISHED_TTL_SECS`` ago.
        2. CAP: once there are more than ``_FINISHED_CAP`` terminal, unsubscribed
           jobs, evict the oldest-finished first until the cap holds again — so a
           long session that starts many short-lived jobs can't outgrow memory
           even if each one individually ages out fast enough to dodge rule 1.

        A running job is NEVER a candidate (``finished_at is None`` guards it out
        of both rules). ``_active`` entries pointing at an evicted job id are
        cleaned up too, so a stale id can't linger there (harmless either way —
        the single-flight check already requires ``status == "running"`` — but
        tidier and cheaper to check).
        """
        now = time.monotonic()
        evictable = [
            j for j in self._jobs.values()
            if j.finished_at is not None and not j.has_subscribers()
        ]

        to_evict: set[str] = set()
        for j in evictable:
            if now - j.finished_at > _FINISHED_TTL_SECS:
                to_evict.add(j.id)

        remaining = [j for j in evictable if j.id not in to_evict]
        overflow = len(remaining) - _FINISHED_CAP
        if overflow > 0:
            remaining.sort(key=lambda j: j.finished_at)
            for j in remaining[:overflow]:
                to_evict.add(j.id)

        if not to_evict:
            return
        for jid in to_evict:
            self._jobs.pop(jid, None)
        stale_gates = [g for g, jid in self._active.items() if jid in to_evict]
        for g in stale_gates:
            self._active.pop(g, None)

    def start(self, kind: str, key: str, fn: Callable[[JobHandle], Any],
              *, exclusive: bool = False) -> str:
        """Launch ``fn(handle)`` on a daemon thread; return the new job id.

        Single-flight: if a job with the same ``(kind, key)`` is still running,
        raise :class:`JobConflict` (``same_gate=True``) carrying that job's id
        (route -> 409). This is the serialization guarantee that makes the per-run
        engine-global reset below safe.

        ``exclusive=True`` additionally enforces a PROCESS-WIDE engine mutex: at
        most one exclusive job may run at a time across the whole process, even for
        a DIFFERENT ``(kind, key)``. A second exclusive start while one is in flight
        raises :class:`JobConflict` with ``same_gate=False`` carrying the running
        exclusive job's id. This is what stops two different projects from ingesting
        concurrently in-process — the engine's per-run process globals
        (``applog._WARNED_ONCE`` / ``discoverer._RUN_QUERY_MEMO``) and the
        single-active-project path assume strictly serial engine runs. The
        exclusive slot is released in ``finish()`` (success, failure, or cancel).
        """
        gate = (str(kind), str(key))
        job_id = uuid.uuid4().hex
        with self._lock:
            self._evict_finished_locked()
            # Same-(kind,key) single-flight (applies to every job).
            running = self._active.get(gate)
            if running is not None and running in self._jobs \
                    and self._jobs[running].status == "running":
                raise JobConflict(running, same_gate=True)
            # Process-wide exclusive mutex (engine jobs only). A different
            # exclusive job already holding the slot blocks this one.
            if exclusive and self._exclusive_active is not None:
                holder = self._jobs.get(self._exclusive_active)
                if holder is not None and holder.status == "running":
                    raise JobConflict(self._exclusive_active, same_gate=False)
                # Holder finished without releasing (shouldn't happen — finish()
                # releases — but never wedge the mutex on a stale id).
                self._exclusive_active = None
            job = _Job(job_id, str(kind), str(key))
            job.exclusive = exclusive
            self._jobs[job_id] = job
            self._active[gate] = job_id
            if exclusive:
                self._exclusive_active = job_id

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
                try:
                    result = fn(handle)
                except Exception as exc:  # noqa: BLE001 — capture ANY failure for status
                    job.finish("failed", None, f"{type(exc).__name__}: {exc}")
                    return
                status = "cancelled" if job.cancel_event.is_set() else "done"
                job.finish(status, result, None)
            finally:
                # ALWAYS release the process-wide exclusive slot when an exclusive
                # job leaves the running state (done / failed / cancelled), so the
                # next engine job can start. Guarded by the runner lock and a
                # same-id check so a late release can't clear a slot a *newer*
                # exclusive job already holds.
                if exclusive:
                    with self._lock:
                        if self._exclusive_active == job_id:
                            self._exclusive_active = None

        t = threading.Thread(target=_run, name=f"job-{kind}-{job_id[:8]}",
                             daemon=True)
        t.start()
        return job_id

    def exclusive_active(self) -> Optional[str]:
        """The id of the in-flight EXCLUSIVE engine job (daily run / search /
        build-list / seed-metro), or None when no exclusive engine job is running.
        Lets a NON-job data-folder mutation (e.g. backup/restore, which extracts
        over ``config.USER_DATA_DIR`` and is not itself a JobRunner job) refuse to
        run while an engine job is reading/writing that same folder — the same
        serialization guarantee the exclusive mutex gives engine jobs against each
        other. A stale holder id (finished without releasing — shouldn't happen)
        reads as None."""
        with self._lock:
            holder_id = self._exclusive_active
            if holder_id is None:
                return None
            holder = self._jobs.get(holder_id)
            if holder is not None and holder.status == "running":
                return holder_id
            return None

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

    def replay_lines(self, job_id: str) -> list[str]:
        """Public snapshot of a job's buffered log lines for SSE replay. Returns
        an empty list for an unknown job. Replaces the SSE route reaching into
        ``_get().lines`` internals.

        KNOWN benign boundary duplication: the SSE route replays this snapshot and
        THEN drains the live subscriber queue. Because it subscribes and snapshots
        without an atomic barrier between them, a single line landing in that gap
        can appear BOTH in the replay and in the live drain. SSE consumers must
        therefore render lines idempotently — the frontend console should de-dupe
        consecutive identical frames (or otherwise tolerate a repeated boundary
        line). This is intentional: the alternative (a lock spanning subscribe +
        snapshot + first drain) would couple loggers to the slow HTTP generator.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return []
            with job._lock:
                return list(job.lines)

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
