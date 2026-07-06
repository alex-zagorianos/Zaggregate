"""B1: GUI core-loop plumbing that does NOT need a Tk display.

Covers the scheduler helper (schtasks command construction, mocked), the
run_daily_ingest pin pattern, the frozen `--daily` arg parsing, the jobhive
flag passthrough, and the browser-receiver embedding pin — all headless.
"""
import sys
import types

import pytest


# ── scheduler helper: schtasks command construction (mocked) ──────────────────

def _capture_schtasks(monkeypatch):
    """Patch subprocess.run inside scripts.setup_schedule to record argv and
    return rc=0. Returns the list that will collect each call's argv."""
    import scripts.setup_schedule as sched
    calls = []

    class _R:
        returncode = 0
        stdout = ""

    def fake_run(cmd, *a, **k):
        calls.append(cmd)
        return _R()

    monkeypatch.setattr(sched.subprocess, "run", fake_run)
    return sched, calls


def test_register_daily_task_dev_builds_py_command(monkeypatch):
    sched, calls = _capture_schtasks(monkeypatch)
    monkeypatch.setattr(sched, "_is_frozen", lambda: False)
    rc = sched.register_daily_task("myproj", "07:30")
    assert rc == 0
    cmd = calls[-1]
    assert cmd[0] == "schtasks" and "/Create" in cmd and "/F" in cmd
    assert "/TN" in cmd and "JobSearchDaily_myproj" in cmd
    tr = cmd[cmd.index("/TR") + 1]
    assert "py src\\daily_run.py --project myproj" in tr
    assert ">>" in tr and "2>&1" in tr           # log redirect present
    assert "07:30" in cmd                         # start time honored


def test_register_daily_task_frozen_builds_exe_daily_command(monkeypatch):
    sched, calls = _capture_schtasks(monkeypatch)
    monkeypatch.setattr(sched, "_is_frozen", lambda: True)
    monkeypatch.setattr(sched.sys, "executable", r"C:\App\JobProgram.exe")
    sched.register_daily_task("dad")
    tr = calls[-1][calls[-1].index("/TR") + 1]
    assert "--daily --project dad" in tr
    assert "JobProgram.exe" in tr
    assert ">>" in tr and "2>&1" in tr


def test_unregister_daily_task_deletes(monkeypatch):
    sched, calls = _capture_schtasks(monkeypatch)
    sched.unregister_daily_task("gone")
    cmd = calls[-1]
    assert "/Delete" in cmd and "JobSearchDaily_gone" in cmd and "/F" in cmd


def test_task_status_parses_next_run(monkeypatch):
    import scripts.setup_schedule as sched

    class _R:
        returncode = 0
        stdout = ("Folder: \\\nHostName: PC\nTaskName: \\JobSearchDaily_x\n"
                  "Next Run Time: 6/2/2026 7:30:00 AM\nStatus: Ready\n")

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: _R())
    st = sched.task_status("x")
    assert st["registered"] is True
    assert st["next_run"] == "6/2/2026 7:30:00 AM"


def test_task_status_not_registered_on_nonzero(monkeypatch):
    import scripts.setup_schedule as sched

    class _R:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: _R())
    st = sched.task_status("nope")
    assert st["registered"] is False and st["next_run"] == ""


def test_start_time_stagger():
    import scripts.setup_schedule as sched
    assert sched._start_time(0) == "07:30"
    assert sched._start_time(1) == "07:35"
    assert sched._start_time(2) == "07:40"


# ── run_daily_ingest: S27-safe pin pattern ────────────────────────────────────

def test_run_daily_ingest_pins_before_ingest_and_unpins_after(monkeypatch):
    import gui
    import workspace

    events = []
    monkeypatch.setattr(workspace, "pin_active",
                        lambda slug: events.append(("pin", slug)))
    monkeypatch.setattr(workspace, "unpin_active",
                        lambda: events.append(("unpin", None)))

    fake_daily = types.ModuleType("daily_run")

    def fake_run_main():
        # The pin MUST already be set before any ingest work runs.
        assert ("pin", "proj-a") in events
        events.append(("ran", "proj-a"))
        return 0

    fake_daily.run_main = fake_run_main
    monkeypatch.setitem(sys.modules, "daily_run", fake_daily)

    rc = gui.run_daily_ingest("proj-a")
    assert rc == 0
    # Order: pin -> ran -> unpin
    assert events == [("pin", "proj-a"), ("ran", "proj-a"), ("unpin", None)]


def test_run_daily_ingest_unpins_even_on_error(monkeypatch):
    import gui
    import workspace
    events = []
    monkeypatch.setattr(workspace, "pin_active",
                        lambda slug: events.append("pin"))
    monkeypatch.setattr(workspace, "unpin_active",
                        lambda: events.append("unpin"))
    monkeypatch.setattr(workspace, "active_slug", lambda: "x")

    fake_daily = types.ModuleType("daily_run")
    fake_daily.run_main = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "daily_run", fake_daily)

    with pytest.raises(RuntimeError):
        gui.run_daily_ingest("x")
    assert events[0] == "pin" and events[-1] == "unpin"


def test_run_daily_ingest_restores_argv(monkeypatch):
    import gui
    import workspace
    monkeypatch.setattr(workspace, "pin_active", lambda slug: None)
    monkeypatch.setattr(workspace, "unpin_active", lambda: None)
    fake_daily = types.ModuleType("daily_run")
    captured = {}

    def rm():
        captured["argv"] = list(sys.argv)
        return 0
    fake_daily.run_main = rm
    monkeypatch.setitem(sys.modules, "daily_run", fake_daily)

    before = list(sys.argv)
    gui.run_daily_ingest("slugX")
    assert sys.argv == before                       # restored
    assert captured["argv"] == ["daily_run.py", "--project", "slugX"]


def test_line_sink_forwards_whole_lines():
    import gui
    got = []
    s = gui._LineSink(got.append)
    s.write("hello ")
    s.write("world\npartial")
    assert got == ["hello world"]                   # only the complete line
    s.flush()
    assert got == ["hello world", "partial"]         # flush drains the buffer


# ── frozen --daily arg parsing ────────────────────────────────────────────────

def test_headless_daily_parses_project(monkeypatch):
    import gui
    seen = {}

    def fake(slug):
        seen["slug"] = slug
        return 0
    monkeypatch.setattr(gui, "run_daily_ingest", fake)
    rc = gui._run_headless_daily(["--daily", "--project", "dad"])
    assert rc == 0 and seen["slug"] == "dad"


def test_headless_daily_defaults_to_active(monkeypatch):
    import gui
    import workspace
    monkeypatch.setattr(workspace, "active_slug", lambda: "active-one")
    seen = {}

    def fake(slug):
        seen["slug"] = slug
        return 0
    monkeypatch.setattr(gui, "run_daily_ingest", fake)
    gui._run_headless_daily(["--daily"])
    assert seen["slug"] == "active-one"


def test_main_routes_daily_flag_without_tk(monkeypatch):
    import gui
    called = {}
    monkeypatch.setattr(sys, "argv", ["gui.py", "--daily", "--project", "p"])

    def fake(argv):
        called["argv"] = argv
        return 7
    monkeypatch.setattr(gui, "_run_headless_daily", fake)
    # App() must never be constructed on the --daily path.
    monkeypatch.setattr(gui, "App",
                        lambda: (_ for _ in ()).throw(AssertionError("Tk started")))
    rc = gui.main()
    assert rc == 7 and called["argv"] == ["--daily", "--project", "p"]


# ── jobhive flag passthrough (GUI dialog -> orchestrator) ─────────────────────

def test_build_company_list_accepts_jobhive_kwarg():
    import inspect
    import build_company_list as bcl
    sig = inspect.signature(bcl.build_company_list)
    assert "jobhive" in sig.parameters
    assert sig.parameters["jobhive"].default is False


def test_jobhive_flag_reaches_orchestrator(monkeypatch):
    """The GUI dialog passes jobhive=<checkbox> to build_company_list; assert the
    kwarg is honored end-to-end by stubbing the jobhive stage."""
    import build_company_list as bcl
    calls = []
    monkeypatch.setattr(bcl, "_jobhive_stage",
                        lambda industry, dry_run, log=print: calls.append(industry) or {})
    # Give it a resolvable field so it doesn't raise, and neuter the other stages.
    monkeypatch.setattr(bcl, "_resolve_field",
                        lambda explicit, project, key: "nursing" if key == "industry" else "")
    monkeypatch.setattr(bcl, "_harvest_inbox", lambda *a, **k: {})
    monkeypatch.setattr(bcl, "registry_stats", lambda: {})
    monkeypatch.setattr(bcl, "loop_signal", lambda *a, **k: "rising")
    monkeypatch.setattr(bcl, "load_history", lambda *a, **k: {})
    out = bcl.build_company_list(industry="nursing", metro=None,
                                 use_inbox=False, jobhive=True, log=lambda *a, **k: None)
    assert calls == ["nursing"]            # jobhive stage ran because flag=True
    assert out["stages"]["jobhive"] is not None


def test_jobhive_off_skips_stage(monkeypatch):
    import build_company_list as bcl
    ran = []
    monkeypatch.setattr(bcl, "_jobhive_stage",
                        lambda *a, **k: ran.append(1) or {})
    monkeypatch.setattr(bcl, "_resolve_field",
                        lambda explicit, project, key: "nursing" if key == "industry" else "")
    monkeypatch.setattr(bcl, "_harvest_inbox", lambda *a, **k: {})
    monkeypatch.setattr(bcl, "registry_stats", lambda: {})
    monkeypatch.setattr(bcl, "loop_signal", lambda *a, **k: "rising")
    monkeypatch.setattr(bcl, "load_history", lambda *a, **k: {})
    out = bcl.build_company_list(industry="nursing", use_inbox=False,
                                 jobhive=False, log=lambda *a, **k: None)
    assert ran == []
    assert out["stages"]["jobhive"] is None


# ── browser-receiver embedding: must NOT take the process-wide pin ────────────
# (Review-fleet critical: an embedded receiver pin silently overrides the GUI
#  project switcher for the whole process — the exact S27 misrouting class.)

def test_receiver_start_in_thread_never_pins_process(monkeypatch):
    from scrape import browser_receiver as br
    pins = []
    monkeypatch.setattr(br.workspace, "pin_active", lambda slug: pins.append(slug))

    started = {}

    def fake_run(*a, **k):
        started["ran"] = True

    monkeypatch.setattr(br.app, "run", fake_run)
    # Avoid a real thread: run the target synchronously.

    class _T:
        def __init__(self, target, **k):
            self._target = target
        def start(self):
            self._target()
        def is_alive(self):
            return True

    monkeypatch.setattr(br._threading, "Thread", _T)
    monkeypatch.setattr(br, "_SERVER_THREAD", None, raising=False)

    br.start_in_thread("proj-x")
    assert pins == []                       # embedded mode NEVER pins the process
    assert started.get("ran") is True


def test_receiver_wait_until_listening_false_when_thread_dead(monkeypatch):
    from scrape import browser_receiver as br

    class _Dead:
        def is_alive(self):
            return False

    monkeypatch.setattr(br, "_SERVER_THREAD", _Dead(), raising=False)
    # Probe a port that is guaranteed FREE (bind :0, note it, close) instead of
    # the real receiver port — a LIVE receiver on 5002 (the GUI's embedded one
    # during a manual extension-test session) flipped this assert to True
    # (found live 2026-07-02). The unit under test is the dead-thread
    # fast-path, not the shared real port.
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    monkeypatch.setattr(br, "PORT", free_port)
    # Nothing is listening on the port and the thread is dead -> fast False.
    assert br.wait_until_listening(timeout=0.5) is False


def test_receiver_capture_count_bumps():
    from scrape import browser_receiver as br
    before = br.capture_count()
    br._bump_capture(3)
    assert br.capture_count() == before + 3
