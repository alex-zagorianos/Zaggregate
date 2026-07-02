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


@pytest.fixture
def root_demo(tmp_path, monkeypatch):
    """A fresh first-run root where the sample DEMO inbox is ACTIVE (empty real
    inbox, demo not retired) — so the export-leak guard is under test."""
    import config
    import demo_data
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    db.init_db()
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    r.withdraw()
    gui.theme.apply_theme(r)
    yield r
    r.destroy()


def test_export_rows_never_include_demo_rows(root_demo):
    # With an empty real inbox the InboxTab activates the sample demo overlay.
    tab = gui.InboxTab(root_demo)
    tab.refresh()
    assert tab._demo_active is True and tab._all      # demo is on screen
    assert all(r.get("is_demo") for r in tab._all)
    # _export_rows must strip demo rows for BOTH scopes (defense in depth), so a
    # fictional job can never reach the AI round-trip via any path.
    tab._export_scope.set("Entire inbox")
    assert tab._export_rows() == []
    tab._export_scope.set("Current view")
    assert tab._export_rows() == []


def test_export_for_ai_blocked_while_demo_active_then_works_after_retire(
        root_demo, tmp_path, monkeypatch):
    import config
    import demo_data
    from rerank import export as rerank_export
    tab = gui.InboxTab(root_demo)
    tab.refresh()
    assert tab._demo_active is True

    # While the demo is active, export must be BLOCKED with the sample-inbox
    # info dialog and must never call the exporter.
    infos = []
    monkeypatch.setattr(gui.messagebox, "showinfo",
                        lambda *a, **k: infos.append(a))
    called = {"n": 0}

    def _fake_export(*a, **k):
        called["n"] += 1
        return {"csv": "x.csv", "md": "x.md", "prompt": "prompt.md"}
    monkeypatch.setattr(rerank_export, "export_inbox", _fake_export)
    tab._export_for_ai()
    assert called["n"] == 0                      # exporter never ran
    assert infos and "Sample inbox" in infos[-1][0]

    # After a real inbox exists the demo retires; export then runs on real rows.
    demo_data.retire_demo(config.USER_DATA_DIR)
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO inbox (norm_url, title, company, location, url, source, "
            "score, date_added) VALUES (?,?,?,?,?,?,?,?)",
            ("acme.test/job/1", "Controls Engineer", "Acme", "Cincinnati, OH",
             "https://acme.test/job/1", "adzuna", 88, "2026-07-01"))
        conn.commit()
    tab.refresh()
    assert tab._demo_active is False
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: None)
    tab._export_scope.set("Entire inbox")
    tab._export_for_ai()
    assert called["n"] == 1                      # real export ran exactly once
