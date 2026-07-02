"""S32/L1 (P0-4): a scoped `daily_run.py --project X` run must NOT rewrite the
GLOBAL projects.json 'active'. Before the fix, main() called
workspace.set_active(args.project), persistently flipping which project the
user's GUI opens to next launch as a side effect of a scoped run. The S27
process-local pin already isolates the run, so set_active was removed.

These tests exercise the real main() up to the point it aborts on "no sources"
(build_clients stubbed to []), which runs the entire set_active region + pin but
does no network — proving the invariant end-to-end.
"""
import inspect
import sys

import pytest

import daily_run
import workspace
from tracker import db


@pytest.fixture
def two_projects(tmp_path, monkeypatch):
    """A real temp registry with projects A (active) and B, plus DB redirected to
    temp so main()'s init_db/record_run_* land somewhere writable."""
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    a = workspace.create_project("Project A", make_active=True)
    b = workspace.create_project("Project B")
    assert workspace.active_slug() == a
    # Point the tracker DB at a temp file (main() opens it for the runs beacon).
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    # Keep main() offline + quiet, and abort right after the pin: no sources ->
    # main() records a failed run and sys.exit(1) BEFORE any search work, but
    # AFTER the whole set_active region + pin have executed.
    import search.cli as cli
    monkeypatch.setattr(cli, "build_clients", lambda *a, **k: [])
    import userdata
    monkeypatch.setattr(userdata, "bootstrap", lambda *a, **k: None)
    monkeypatch.setattr(daily_run, "log", lambda *a, **k: None)
    return a, b


def _run(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", argv)
    try:
        daily_run.main()
    except SystemExit:
        pass
    finally:
        workspace.unpin_active()  # main() doesn't unpin; run_main's finally does


def test_scoped_project_run_leaves_active_untouched(two_projects, monkeypatch):
    a, b = two_projects
    _run(["daily_run.py", "--project", b], monkeypatch)
    # The scoped run must NOT have flipped the global pointer to B.
    assert workspace.active_slug() == a


def test_scoped_project_run_pins_to_requested_project(two_projects, monkeypatch):
    """Sanity: while pinned during the run, resolution goes to the requested
    project (the isolation the run actually needs) — captured mid-run."""
    a, b = two_projects
    seen = {}

    import search.cli as cli

    def _capture(*args, **kwargs):
        # Called after main() has pinned; the pin must resolve to B here.
        seen["pinned"] = workspace.active_slug()
        return []

    monkeypatch.setattr(cli, "build_clients", _capture)
    _run(["daily_run.py", "--project", b], monkeypatch)
    assert seen["pinned"] == b          # in-process resolution followed the pin
    assert workspace.active_slug() == a  # ...but disk 'active' is still A


def test_default_run_without_project_leaves_active_untouched(two_projects, monkeypatch):
    a, b = two_projects
    _run(["daily_run.py"], monkeypatch)
    assert workspace.active_slug() == a


def test_main_source_no_longer_calls_set_active():
    """Encode the fix so a future refactor can't silently reintroduce the global
    flip (mirrors the --max-pages source-guard convention)."""
    src = inspect.getsource(daily_run.main)
    assert "workspace.set_active(" not in src
