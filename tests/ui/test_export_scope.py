import tkinter as tk
import pytest
import tracker.db as db
import gui


@pytest.fixture
def root_tmpdb(tmp_path, monkeypatch):
    import config
    import demo_data
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    # Isolate the user-data dir + retire the first-run sample inbox so it never
    # activates for a test that swaps in its own real rows.
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    demo_data.retire_demo(tmp_path)
    db.init_db()
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    r.withdraw()
    gui.theme.apply_theme(r)
    yield r
    r.destroy()


def _row(i, score, location):
    return {"id": i, "score": score, "fit": -1, "title": f"T{i}", "company": "X",
            "location": location, "salary_text": "", "source": "s",
            "date_added": "2026-06-22", "board_count": -1, "description": "",
            "fit_why": "", "score_notes": "", "url": ""}


def test_export_scope_entire_vs_view(root_tmpdb):
    tab = gui.InboxTab(root_tmpdb)
    tab._all = [_row(1, 90, "Cincinnati, OH"), _row(2, 10, "Cincinnati, OH")]
    tab._f_location.set("All locations")   # isolate the min-score filter
    tab._f_minscore.set("50")              # view drops id 2
    tab._export_scope.set("Entire inbox")
    assert {r["id"] for r in tab._export_rows()} == {1, 2}
    tab._export_scope.set("Current view")
    assert {r["id"] for r in tab._export_rows()} == {1}
