"""_validate_worker exception guard (finding #18).

Every OTHER background-thread worker in the codebase (ui/tab_inbox.py,
ui/tab_queue.py, ui/tab_search.py, ui/tab_resume.py, ui/seed_area.py, and this
same file's _run_orchestrator) wraps its body in try/except so a single bad
iteration/call can't kill the daemon thread silently. AddCompaniesDialog.
_validate_worker used to be the one exception. This pins the fix: a
probe_board() failure for one entry is reported as "error" (routed to
"unreachable" in _status_by_idx, the safe/unknown-is-unsafe default) and the
loop continues to the remaining entries, and _validate_done always fires
(re-enabling the Validate/Detect buttons) even when a probe raised.
"""
import tkinter as tk

import pytest

import config
import workspace
from scrape.company_registry import CompanyEntry


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "COMPANIES_JSON", tmp_path / "companies.json")
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
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


def _dialog_with_entries(root, entries):
    import gui
    dlg = gui.AddCompaniesDialog(root)
    dlg._entries = list(entries)
    for r in dlg._tree.get_children():
        dlg._tree.delete(r)
    for i, e in enumerate(entries):
        dlg._tree.insert("", "end", iid=str(i),
                         values=(e.name, e.ats_type, e.slug, "-"))
    return dlg


def test_validate_worker_survives_one_bad_probe_and_keeps_going(root, monkeypatch):
    entries = [
        CompanyEntry(name="Good Co", ats_type="greenhouse", slug="goodco"),
        CompanyEntry(name="Boom Co", ats_type="greenhouse", slug="boomco"),
        CompanyEntry(name="Also Good", ats_type="greenhouse", slug="alsogood"),
    ]
    dlg = _dialog_with_entries(root, entries)

    class _FakeProbe:
        def __init__(self, reachable, count):
            self.reachable = reachable
            self.count = count

    def fake_probe_board(entry):
        if entry.slug == "boomco":
            raise RuntimeError("simulated network blowup")
        return _FakeProbe(reachable=True, count=3)

    monkeypatch.setattr("scrape.ats_detect.probe_board", fake_probe_board)

    dlg._val_btn.config(state="disabled")
    dlg._detect_btn.config(state="disabled")
    # Run the worker body directly (synchronously, same thread) -- the method
    # itself contains no threading; only its caller (_validate) starts a Thread.
    dlg._validate_worker(list(entries))
    root.update()  # flush the self.after(0, ...) queue

    assert dlg._status_by_idx[0] == "live"
    assert dlg._status_by_idx[1] == "unreachable"   # the bad entry, not crashed-and-lost
    assert dlg._status_by_idx[2] == "live"           # the loop continued past the failure
    # _validate_done fired despite the mid-loop exception -> buttons re-enabled.
    assert str(dlg._val_btn.cget("state")) == "normal"
    assert str(dlg._detect_btn.cget("state")) == "normal"
    dlg.destroy()


def test_validate_worker_all_entries_fail_still_calls_validate_done(root, monkeypatch):
    entries = [CompanyEntry(name="Boom", ats_type="greenhouse", slug="boom")]
    dlg = _dialog_with_entries(root, entries)

    def always_boom(entry):
        raise RuntimeError("network down")

    monkeypatch.setattr("scrape.ats_detect.probe_board", always_boom)

    dlg._val_btn.config(state="disabled")
    dlg._detect_btn.config(state="disabled")
    dlg._validate_worker(list(entries))
    root.update()

    assert dlg._status_by_idx[0] == "unreachable"
    assert str(dlg._val_btn.cget("state")) == "normal"
    assert str(dlg._detect_btn.cget("state")) == "normal"
    dlg.destroy()


def test_validate_worker_direct_entries_still_marked_manual(root, monkeypatch):
    """A 'direct' entry never calls probe_board at all -- confirm the guard
    doesn't disturb that pre-existing short-circuit."""
    entries = [CompanyEntry(name="Direct Co", ats_type="direct", slug="https://x/careers")]
    dlg = _dialog_with_entries(root, entries)

    def unexpected_probe(entry):
        raise AssertionError("probe_board must not be called for a direct entry")

    monkeypatch.setattr("scrape.ats_detect.probe_board", unexpected_probe)

    dlg._validate_worker(list(entries))
    root.update()

    assert dlg._status_by_idx[0] == "direct"
    dlg.destroy()
