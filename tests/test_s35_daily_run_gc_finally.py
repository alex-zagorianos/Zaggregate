"""S35 finding #36 (minor): cache GC only ran at the very end of a SUCCESSFUL
daily_run (inside main() itself), so an aborted/crashed run never trimmed
cache/. Moved into run_main()'s finally: (via the new _gc_cache() helper) so
GC now runs unconditionally after every run -- success, "zero", or a crash --
while preserving ordering (still runs strictly after everything main() did)
and never letting a GC failure mask the run's real outcome/exception."""
import daily_run


def test_gc_runs_after_a_successful_main(monkeypatch):
    calls = []
    monkeypatch.setattr(daily_run, "main", lambda: None)
    monkeypatch.setattr(daily_run, "_gc_cache", lambda: calls.append("gc"))
    monkeypatch.setattr(daily_run.workspace, "unpin_active", lambda: calls.append("unpin"))
    rc = daily_run.run_main()
    assert rc == 0
    assert calls == ["gc", "unpin"]  # GC still runs before the unpin, ordering preserved


def test_gc_still_runs_when_main_raises(monkeypatch):
    # The core of the finding: an ABORTED run (main() raises) must still GC.
    calls = []

    def boom():
        raise RuntimeError("kaboom")
    monkeypatch.setattr(daily_run, "main", boom)
    monkeypatch.setattr(daily_run, "log", lambda msg: None)
    monkeypatch.setattr(daily_run, "_gc_cache", lambda: calls.append("gc"))
    monkeypatch.setattr(daily_run.workspace, "unpin_active", lambda: calls.append("unpin"))
    rc = daily_run.run_main()
    assert rc == 1                     # the crash is still reported as failed
    assert calls == ["gc", "unpin"]     # but GC ran anyway


def test_gc_failure_does_not_mask_the_original_exception(monkeypatch):
    # A GC error inside the finally: must not change run_main()'s return value
    # or raise past it -- the ORIGINAL crash is what gets reported.
    logged = []

    def boom():
        raise RuntimeError("original failure")
    monkeypatch.setattr(daily_run, "main", boom)
    monkeypatch.setattr(daily_run, "log", lambda msg: logged.append(msg))

    def gc_boom():
        raise OSError("disk full during GC")
    monkeypatch.setattr(daily_run, "_gc_cache", gc_boom)
    monkeypatch.setattr(daily_run.workspace, "unpin_active", lambda: None)

    # _gc_cache raising would propagate out of the bare finally: block and
    # replace the original exception/return value -- this must not happen.
    rc = daily_run.run_main()
    assert rc == 1
    assert any("original failure" in m for m in logged)


def test_gc_runs_on_the_zero_jobs_path_too(monkeypatch):
    # A "zero new jobs" run is not an exception (main() returns normally) but
    # must still GC -- covered by the successful-main case, restated for the
    # specific "successful run that found nothing" framing in the finding.
    calls = []
    monkeypatch.setattr(daily_run, "main", lambda: None)  # completes normally
    monkeypatch.setattr(daily_run, "_gc_cache", lambda: calls.append("gc"))
    monkeypatch.setattr(daily_run.workspace, "unpin_active", lambda: None)
    daily_run.run_main()
    assert calls == ["gc"]


def test_gc_cache_helper_is_best_effort_and_logs_on_failure(monkeypatch, tmp_path):
    # _gc_cache() itself must swallow a GC error and log a WARN, never raise --
    # this is what makes it safe to call unconditionally from run_main()'s
    # finally: without an extra guard at the call site.
    import scrape.cache_helpers as ch
    logged = []
    monkeypatch.setattr(daily_run, "log", lambda msg: logged.append(msg))
    monkeypatch.setattr(ch, "gc_cache_dir",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    daily_run._gc_cache()  # must not raise
    assert any("cache GC skipped" in m for m in logged)
