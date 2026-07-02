"""B1: Tk-dependent core-loop UI (headless-safe; skips when no display).

Covers the empty-state copy, the Inbox 'Update my Inbox now' worker (pin
pattern + single-flight guard), bulk 'Dismiss all shown' + undo, the wizard
closing 'Keep jobs coming' step, and the BuildCompanyListDialog jobhive/paste
additions. Follows the repo's existing ui test pattern (seed a temp DB, build a
Tk root, skip on TclError).
"""
import tkinter as tk

import pytest

from tracker import db
import workspace


@pytest.fixture
def root(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    # Isolate the user-data dir so the first-run sample-inbox marker is
    # deterministic (and never touches the real machine's marker).
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    db.init_db()
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    import gui
    gui.theme.apply_theme(r)
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def _seed_inbox(n=3):
    from models import JobResult
    jobs = []
    for i in range(n):
        jobs.append(JobResult(
            title=f"Nurse {i}", company=f"Hospital{i}", location="Remote",
            salary_min=None, salary_max=None, description="", url=f"https://x/{i}",
            source_keyword="k", created="2026-06-01", job_id="", source_api="muse"))
    db.inbox_add_many(jobs)


# ── empty-state copy points at 'Update my Inbox now' (not Search) ─────────────

def test_inbox_empty_state_copy_updated(root):
    import gui
    import config
    import demo_data
    # Returning-user empty state (not first-run demo): retire the sample inbox.
    demo_data.retire_demo(config.USER_DATA_DIR)
    tab = gui.InboxTab(root)
    root.update_idletasks()
    assert tab._empty_widget is not None
    # Pull all label text out of the empty-state overlay (labels live a couple
    # levels deep inside the frame).
    texts = []

    def _walk(w):
        try:
            texts.append(str(w.cget("text")))
        except tk.TclError:
            pass
        for c in w.winfo_children():
            _walk(c)
    _walk(tab._empty_widget)
    blob = " ".join(texts)
    assert "Update my Inbox now" in blob
    # The old lie ("click Search — matches land here") is gone.
    assert "click Search" not in blob


# ── §6.1 bundled sample inbox (first-run demo) ────────────────────────────────

def test_first_run_shows_demo_inbox(root):
    """A fresh, empty inbox with the demo not yet retired shows the sample rows
    (no empty overlay), the demo banner, and marks the tab in demo mode."""
    import gui
    tab = gui.InboxTab(root)
    root.update_idletasks()
    assert tab._demo_active is True
    assert tab._empty_widget is None                 # demo replaces empty state
    assert tab._all and all(r.get("is_demo") for r in tab._all)
    # banner is packed (winfo_ismapped needs a shown root; pack_info is enough)
    assert tab._demo_banner.pack_info()              # raises/empty if not packed
    assert "DEMO" in tab._demo_banner.cget("text")


def test_demo_rows_cannot_be_tracked_or_dismissed(root, monkeypatch):
    """Triage on a demo row is blocked (no DB write on a synthetic negative id)."""
    import gui
    # The guard shows an info modal in real use; stub it so the headless test
    # doesn't block on it.
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *a, **k: None)
    tab = gui.InboxTab(root)
    root.update_idletasks()
    demo_sel = [tab._all[0]]
    assert tab._block_if_demo(demo_sel) is True      # guard fires
    # a real (non-demo) row is NOT blocked
    assert tab._block_if_demo([{"is_demo": False}]) is False


def test_update_now_retires_demo(root, monkeypatch):
    """Clicking Update retires the sample inbox immediately so it never returns,
    even if the run adds zero real rows."""
    import gui
    import config
    import demo_data
    tab = gui.InboxTab(root)
    root.update_idletasks()
    assert tab._demo_active is True
    monkeypatch.setattr(workspace, "active_slug", lambda: "p1")
    # Run the worker inline (no background thread) so no stray self.after fires
    # after the test root is torn down.
    monkeypatch.setattr(gui.threading, "Thread",
                        lambda *a, **k: type("T", (), {"start": lambda self: None,
                                                       "daemon": True})())
    monkeypatch.setattr(gui, "run_daily_ingest", lambda slug, on_line=None: 0)
    tab._update_inbox_now()
    # Retire is synchronous (happens before the worker), so it's already done.
    assert demo_data.is_demo_retired(config.USER_DATA_DIR) is True


def test_inbox_update_button_exists(root):
    import gui
    tab = gui.InboxTab(root)
    assert hasattr(tab, "_update_btn")
    assert tab._update_running is False


# ── Update my Inbox now: pin pattern + single-flight ──────────────────────────

def test_update_inbox_now_pins_and_runs(root, monkeypatch):
    import gui
    tab = gui.InboxTab(root)
    events = []
    monkeypatch.setattr(workspace, "active_slug", lambda: "proj-1")

    def fake_ingest(slug, on_line=None):
        events.append(("ingest", slug))
        if on_line:
            on_line("[Muse] 5 results in ~1.0s")
        return 0
    monkeypatch.setattr(gui, "run_daily_ingest", fake_ingest)

    # Run the worker synchronously (Tk 'after' from a non-main thread is flaky in
    # a headless test) so completion is deterministic; the pin/flag logic is what
    # matters here, not the thread itself.
    class _T:
        def __init__(self, target, **k):
            self._target = target
        def start(self):
            self._target()
    monkeypatch.setattr(gui.threading, "Thread", _T)

    tab._update_inbox_now()
    root.update()               # flush the after(0, _update_inbox_done)
    assert ("ingest", "proj-1") in events
    assert tab._update_running is False


def test_update_inbox_now_single_flight(root, monkeypatch):
    import gui
    tab = gui.InboxTab(root)
    tab._update_running = True            # pretend a run is in flight
    called = []
    monkeypatch.setattr(gui, "run_daily_ingest",
                        lambda slug, on_line=None: called.append(1) or 0)
    tab._update_inbox_now()               # must be a no-op
    assert called == []


# ── bulk 'Dismiss all shown' + undo ───────────────────────────────────────────

def test_dismiss_all_shown_and_undo(root, monkeypatch):
    import gui
    _seed_inbox(3)
    tab = gui.InboxTab(root)
    tab.refresh()
    root.update_idletasks()
    assert len(tab._rows) == 3
    # Auto-confirm the yes/no.
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    tab._dismiss_all_shown()
    root.update_idletasks()
    assert db.inbox_count() == 0
    # Undo restores the batch via the same _remember_undo path.
    assert tab._undo_rows and str(tab._undo_btn.cget("state")) == "normal"
    tab._undo_dismiss()
    root.update_idletasks()
    assert db.inbox_count() == 3


def test_select_all_selects_every_row(root):
    import gui
    _seed_inbox(4)
    tab = gui.InboxTab(root)
    tab.refresh()
    root.update_idletasks()
    tab._select_all()
    assert len(tab._tree.selection()) == 4


# ── wizard closing 'Keep jobs coming' step ────────────────────────────────────

def test_wizard_has_keep_going_step(root, monkeypatch):
    from ui import setup_wizard
    # Don't let it actually run maybe_run's onboarded check; construct directly.
    wiz = setup_wizard.SetupWizard(root)
    try:
        assert wiz._step_keep_going in wiz._steps
        assert "daily_updates" in wiz._vars and "build_list" in wiz._vars
        # Both default ON.
        assert wiz._vars["daily_updates"].get() is True
        assert wiz._vars["build_list"].get() is True
    finally:
        wiz.destroy()


def test_wizard_close_passes_actions_to_two_arg_callback(root, monkeypatch):
    from ui import setup_wizard
    got = {}

    def cb(applied, actions):
        got["applied"] = applied
        got["actions"] = actions

    wiz = setup_wizard.SetupWizard(root, on_finish=cb)
    wiz._actions = {"daily_updates": True, "build_list": False,
                    "industry": "nursing", "location": "Remote"}
    wiz._close(applied=True)
    assert got["applied"] is True
    assert got["actions"]["daily_updates"] is True
    assert got["actions"]["industry"] == "nursing"


def test_wizard_close_back_compat_one_arg_callback(root):
    from ui import setup_wizard
    got = {}
    wiz = setup_wizard.SetupWizard(root, on_finish=lambda applied: got.setdefault("a", applied))
    wiz._actions = {"daily_updates": False, "build_list": False}
    wiz._close(applied=False)             # 1-arg cb must still work
    assert got["a"] is False


# ── BuildCompanyListDialog: jobhive checkbox + paste path ─────────────────────

def test_build_list_dialog_has_jobhive_and_paste(root):
    import gui
    dlg = gui.BuildCompanyListDialog(root, default_industry="nursing")
    try:
        assert hasattr(dlg, "_jobhive")
        assert dlg._jobhive.get() is False       # off by default
        assert hasattr(dlg, "_paste_btn")
        assert hasattr(dlg, "_on_paste_reply")
    finally:
        dlg.destroy()


def test_tools_menu_has_new_entries(root, monkeypatch, tmp_path):
    """Construct the App far enough to build its menu, and confirm the new Tools
    entries exist (Turn on daily updates / Capture from browser / Connect job
    sources). Guards against a typo in _build_menu()."""
    import gui
    import userdata
    # Neuter first-run/bootstrap side effects and the wizard so App() builds fast.
    monkeypatch.setattr(userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(gui.setup_wizard, "maybe_run", lambda *a, **k: False)
    try:
        app = gui.App()
    except tk.TclError:
        pytest.skip("no display")
    try:
        # Walk the menubar for a Tools cascade and read its labels.
        labels = []

        def _collect(menu):
            end = menu.index("end")
            if end is None:
                return
            for i in range(end + 1):
                try:
                    labels.append(menu.entrycget(i, "label"))
                except tk.TclError:
                    pass
        menubar = app.nametowidget(app.cget("menu"))
        for i in range(menubar.index("end") + 1):
            try:
                sub = menubar.entrycget(i, "menu")
                if sub:
                    _collect(app.nametowidget(sub))
            except tk.TclError:
                pass
        assert any("Turn on daily updates" in l for l in labels)
        assert any("Capture jobs from my browser" in l for l in labels)
        assert any("Connect job sources" in l for l in labels)
    finally:
        app.destroy()


# ── New Person wizard honors the closing 'Keep jobs coming' step ──────────────

def _build_app(monkeypatch):
    """Construct the App far enough to exercise its methods, neutering first-run
    side effects. Returns the app (caller destroys it) or skips if no display."""
    import gui
    import userdata
    monkeypatch.setattr(userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(gui.setup_wizard, "maybe_run", lambda *a, **k: False)
    try:
        return gui.App()
    except tk.TclError:
        pytest.skip("no display")


def test_new_person_finish_handler_is_two_arg_and_honors_actions(root, monkeypatch):
    """The New Person wizard's finish handler must take (applied, actions) so the
    closing-step choices survive — a 1-arg lambda silently dropped them. Assert
    the handler forwards actions to the shared _after_setup path (daily updates
    registered / Build-My-List opened / forced first inbox update)."""
    import inspect
    import gui
    app = _build_app(monkeypatch)
    try:
        # It is a 2-arg method (so setup_wizard._close detects takes_two=True).
        params = [p for p in inspect.signature(app._after_new_person_setup)
                  .parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        assert len(params) >= 2

        calls = {"daily": 0, "build": 0, "askyesno": 0}
        monkeypatch.setattr(app, "_rebuild_tabs", lambda *a, **k: None)
        monkeypatch.setattr(app, "_update_title", lambda *a, **k: None)
        monkeypatch.setattr(app, "_register_daily_updates",
                            lambda: calls.__setitem__("daily", calls["daily"] + 1))

        class _Dlg:
            def __init__(self, *a, **k):
                calls["build"] += 1
        monkeypatch.setattr(gui, "BuildCompanyListDialog", _Dlg)
        monkeypatch.setattr(app, "wait_window", lambda *a, **k: None)
        # Decline the forced inbox-update prompt so no worker fires; we only need
        # to prove it was reached AFTER the closing-step actions ran.
        monkeypatch.setattr(gui.messagebox, "askyesno",
                            lambda *a, **k: calls.__setitem__(
                                "askyesno", calls["askyesno"] + 1) or False)

        app._after_new_person_setup(
            True, {"daily_updates": True, "build_list": True,
                   "industry": "nursing", "location": "Remote"})
        assert calls["daily"] == 1          # daily updates registered
        assert calls["build"] == 1          # Build-My-List opened
        assert calls["askyesno"] == 1       # forced inbox-update prompt offered
    finally:
        app.destroy()


# ── First-run flow sequences Build-My-List BEFORE the inbox-update prompt ──────

def test_after_setup_waits_for_build_dialog_before_inbox_prompt(root, monkeypatch):
    """_after_setup must wait_window() on the Build-My-List modal before offering
    the 'Update your Inbox now?' prompt, so the two modals don't stack."""
    import gui
    app = _build_app(monkeypatch)
    try:
        order = []
        monkeypatch.setattr(app, "_rebuild_tabs", lambda *a, **k: None)

        class _Dlg:
            def __init__(self, *a, **k):
                order.append("build_open")
        monkeypatch.setattr(gui, "BuildCompanyListDialog", _Dlg)
        monkeypatch.setattr(app, "wait_window",
                            lambda *a, **k: order.append("build_closed"))
        monkeypatch.setattr(gui.messagebox, "askyesno",
                            lambda *a, **k: order.append("inbox_prompt") or False)

        app._after_setup(True, {"daily_updates": False, "build_list": True,
                                "industry": "", "location": ""})
        # The Build dialog is opened, THEN awaited to close, THEN the inbox prompt
        # — never the prompt before the dialog closes.
        assert order == ["build_open", "build_closed", "inbox_prompt"]
    finally:
        app.destroy()


# ── Demo suppresses the real-reach fix badge ──────────────────────────────────

def test_reach_fix_badge_suppressed_while_demo_active(root, monkeypatch):
    """While the first-run sample inbox is on screen, the real-reach '[Connect a
    free key]' fix badge must be suppressed (it would contradict the curated
    demo rows). It reappears once the demo retires."""
    import gui
    import coverage.reach as reach
    # Force a non-empty reach reason so the badge WOULD show if not suppressed.
    monkeypatch.setattr(reach, "badge_reason",
                        lambda *a, **k: "mostly remote/tech jobs")
    monkeypatch.setattr(reach, "badge_line", lambda *a, **k: "reach 40%")
    monkeypatch.setattr(reach, "load_latest", lambda *a, **k: {})
    tab = gui.InboxTab(root)
    tab.refresh()
    assert tab._demo_active is True
    # The fix affordance is empty/hidden while the demo is active.
    assert str(tab._reach_fix_lbl.cget("text")) == ""
    assert str(tab._reach_lbl.cget("text")) == ""
    # After retiring the demo, the reach fix badge is populated again.
    import config
    import demo_data
    demo_data.retire_demo(config.USER_DATA_DIR)
    tab.refresh()
    assert tab._demo_active is False
    assert "mostly remote/tech jobs" in str(tab._reach_fix_lbl.cget("text"))


# ── Board move pushes a refresh to sibling tabs via <<KanbanChanged>> ──────────

def test_kanban_changed_event_is_bound_and_refreshes_siblings(root, monkeypatch):
    """The Board fires <<KanbanChanged>> after a move; the App must bind it and
    refresh the Tracker + Apply Queue views (previously the event was dead)."""
    import gui
    app = _build_app(monkeypatch)
    try:
        hits = {"tracker": 0, "queue": 0}
        monkeypatch.setattr(app._tracker, "refresh",
                            lambda *a, **k: hits.__setitem__("tracker", hits["tracker"] + 1))
        monkeypatch.setattr(app._queue, "refresh",
                            lambda *a, **k: hits.__setitem__("queue", hits["queue"] + 1))
        # The board must carry a binding for the event (not dead).
        assert app._board.bind("<<KanbanChanged>>")
        app._board.event_generate("<<KanbanChanged>>")
        app.update()
        assert hits["tracker"] == 1 and hits["queue"] == 1
    finally:
        app.destroy()


def test_build_list_dialog_passes_jobhive(root, monkeypatch):
    import gui
    dlg = gui.BuildCompanyListDialog(root, default_industry="nursing")
    captured = {}

    def fake_thread_target(**kwargs):
        captured.update(kwargs)

    # Intercept the worker so no real orchestrator/network runs; assert the
    # jobhive flag flows through from the checkbox.
    class _T:
        def __init__(self, target, kwargs=None, **k):
            self._kwargs = kwargs or {}
        def start(self):
            fake_thread_target(**self._kwargs)
    monkeypatch.setattr(gui.threading, "Thread", _T)
    dlg._jobhive.set(True)
    dlg._industry.set("nursing")
    dlg._on_build()
    try:
        assert captured.get("jobhive") is True
        assert captured.get("industry") == "nursing"
    finally:
        dlg.destroy()
