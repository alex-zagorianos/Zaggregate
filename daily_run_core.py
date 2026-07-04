"""Tk-free daily-ingest entry point.

Extracted from ``gui.run_daily_ingest`` (S36 web migration, Phase 3) so the web
backend can run the daily search->score->inbox pipeline WITHOUT importing
``gui``/``tkinter``. ``gui.run_daily_ingest`` is now a thin wrapper that delegates
here, so the frozen exe's ``--daily`` headless path and every existing test that
patches ``gui.run_daily_ingest`` (or swaps ``daily_run`` in ``sys.modules`` and
calls ``gui.run_daily_ingest``) keep working unchanged — the pin/argv/sink/finally
behavior is byte-identical to the pre-extraction gui code.

Design notes carried from the gui version (S27-safe pin pattern):
* Pin the active project BEFORE any db write and unpin in ``finally`` so a
  concurrent run or a project switch can't redirect this run's inbox/output writes
  mid-flight. The pin is process-local; the global active pointer is never touched.
* ``daily_run`` is imported LATE (inside the function) so a test can substitute a
  fake ``daily_run`` module in ``sys.modules`` before the call, and so a headless
  build without the full engine still imports this module.
* ``on_line`` (optional) receives the pipeline's stdout line-by-line via the
  shared ``ui.common._LineSink`` — daily_run narrates with ``print()``, not a
  passed-in sink, so we capture stdout.

Cancel seam: ``daily_run.run_main()`` runs the whole pipeline synchronously and
offers NO in-flight cancel hook, so ``cancel`` here is BEST-EFFORT ONLY — it is
honored before ``run_main()`` starts (a job cancelled while still queued/just
before the heavy work returns 130 without running), but once ``run_main()`` is
executing it runs to completion. This is documented, not a silent no-op; the web
job's cancel button therefore cancels a *pending* daily run, not a mid-flight one.
"""
from __future__ import annotations

import contextlib
import sys
from typing import Callable, Optional

import workspace
from ui.common import _LineSink


def run_ingest(slug, *, on_line: Optional[Callable[[str], None]] = None,
               cancel=None) -> int:
    """Run the daily search->score->inbox pipeline for ONE project, pinned.

    ``slug``   — project slug (falls back to ``workspace.active_slug()``).
    ``on_line`` — optional line sink fed the pipeline's stdout (per-source counts,
                  a 429'd source, an expired key) for live progress.
    ``cancel``  — optional object with ``is_set() -> bool`` (a ``threading.Event``
                  or ``JobHandle.cancelled``). Honored ONLY before ``run_main()``
                  starts (see module docstring — daily_run has no in-flight cancel
                  seam); a run cancelled while pending returns 130 without running.

    Returns daily_run's exit code (0 = ok, 130 = cancelled-before-start).
    """
    import daily_run
    slug = slug or workspace.active_slug()
    prev_argv = sys.argv
    # daily_run.main() re-parses argv and re-pins from --project; pin here too so
    # the pin is live even if that internal pin is ever removed. run_main()'s
    # finally clears the process pin.
    workspace.pin_active(slug)
    sys.argv = ["daily_run.py"] + (["--project", slug] if slug else [])
    sink = _LineSink(on_line) if on_line else None
    try:
        # Best-effort pre-start cancel: if the job was cancelled while queued we
        # skip the heavy pipeline entirely (see module docstring on the missing
        # in-flight seam). 130 = the conventional "terminated" exit code.
        if cancel is not None and getattr(cancel, "is_set", lambda: False)():
            return 130
        if sink is not None:
            with contextlib.redirect_stdout(sink):
                rc = daily_run.run_main()
            sink.flush()
        else:
            rc = daily_run.run_main()
        return rc
    finally:
        sys.argv = prev_argv
        workspace.unpin_active()  # daily_run.run_main already unpins; idempotent
