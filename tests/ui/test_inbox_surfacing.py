"""InboxTab surfacing: colored score cells, the structured detail readout, and the
Hide-stale filter. Pure helpers always; widget construction skipped headlessly."""
import sqlite3

import pytest

from tracker import db


def test_score_cell_static():
    import gui
    assert gui.InboxTab._score_cell(-1) == ""              # unscored -> blank
    # The band color moved to a colored chip in the tree's #0 gutter
    # (ui.chrome.score_chip); the score cell text is now just the number.
    assert gui.InboxTab._score_cell(82) == "82"
    assert gui.InboxTab._score_cell(None) == ""


_COLS = ("norm_url", "url", "title", "company", "location", "salary_text",
         "description", "source", "score", "score_notes", "fit", "fit_why",
         "created", "date_added", "board_count")


def _seed(dbpath):
    conn = sqlite3.connect(str(dbpath))
    placeholders = ",".join("?" * len(_COLS))
    rows = [
        ("k1", "u1", "ML Engineer", "Acme", "Remote", "$120k-$140k",
         "Build ML systems with Kubernetes and Rust.", "careers", 82,
         "title 100% | skills 80% | salary 100% | loc 100% | new 80% | conf 5/5",
         -1, "", "2026-06-20", "2026-06-20", 20),
        ("k2", "u2", "Always Hiring: Talent Community", "Beta", "NY", "",
         "Pipeline role.", "careers", 40,
         "title 50% | loc 50% | conf 2/5", -1, "", "2024-06-01", "2026-06-20", -1),
    ]
    conn.executemany(
        f"INSERT INTO inbox ({','.join(_COLS)}) VALUES ({placeholders})", rows)
    conn.commit()
    conn.close()


@pytest.fixture
def inbox_tab(tmp_path, monkeypatch):
    import tkinter as tk
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    _seed(db.DB_PATH)
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    import gui
    gui.theme.apply_theme(root)
    tab = gui.InboxTab(root)
    yield tab, root
    root.destroy()


def test_detail_text_has_scorecard_and_skill_gap(inbox_tab):
    tab, _ = inbox_tab
    row = next(r for r in tab._all if r["company"] == "Acme")
    text = tab._detail_text(row)
    assert "Score 82" in text
    assert "Title 100%" in text and "Skills 80%" in text
    assert "confidence 5/5" in text
    # the JD wants Kubernetes/Rust which aren't generic noise -> skill-gap line
    assert "Job also wants" in text


def test_empty_inbox_shows_empty_state(tmp_path, monkeypatch):
    import tkinter as tk
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()                     # no rows
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    import gui
    gui.theme.apply_theme(root)
    tab = gui.InboxTab(root)
    try:
        assert tab._empty_widget is not None      # empty-inbox overlay shown
    finally:
        root.destroy()


def test_filtered_to_zero_then_cleared(inbox_tab):
    tab, _ = inbox_tab
    tab._f_minscore.set("999")       # nothing scores this high
    tab._render()
    assert tab._empty_widget is not None
    tab._f_minscore.set("")
    tab._render()
    assert tab._empty_widget is None  # rows visible again -> overlay removed


def test_pay_floor_filter(inbox_tab):
    tab, _ = inbox_tab
    tab._f_location.set("All locations")
    tab._pay_floor = 100000
    for r in tab._all:                # force known comp to isolate the filter logic
        if r["company"] == "Acme":
            r["_comp"] = {"min": 120000, "max": 140000, "disclosed": True,
                          "display": "$120,000–$140,000"}
        else:
            r["_comp"] = {"min": None, "max": None, "disclosed": False,
                          "display": "Not listed"}
    tab._f_floor.set(False)
    assert {r["company"] for r in tab._filtered()} >= {"Acme", "Beta"}
    tab._f_floor.set(True)
    cos = {r["company"] for r in tab._filtered()}
    assert "Acme" in cos and "Beta" not in cos   # undisclosed pay is hidden


def test_hide_stale_filter_drops_evergreen(inbox_tab):
    tab, _ = inbox_tab
    tab._f_location.set("All locations")   # isolate from the location view-filter
    tab._f_hide_stale.set(False)
    assert any(r["company"] == "Beta" for r in tab._filtered())
    tab._f_hide_stale.set(True)
    companies = {r["company"] for r in tab._filtered()}
    assert "Beta" not in companies      # evergreen "Talent Community" is stale
    assert "Acme" in companies          # fresh job kept
