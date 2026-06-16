"""daily_run must log the traceback and return non-zero on failure (2026-06)."""
import daily_run


def test_run_main_logs_and_exits_on_exception(monkeypatch):
    def boom():
        raise RuntimeError("kaboom")
    logged = []
    monkeypatch.setattr(daily_run, "main", boom)
    monkeypatch.setattr(daily_run, "log", lambda msg: logged.append(msg))
    rc = daily_run.run_main()
    assert rc == 1
    assert any("kaboom" in m for m in logged)
