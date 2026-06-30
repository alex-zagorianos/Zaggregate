"""Smoke-build the Tools dialogs (funnel, due) against a seeded temp DB so a
runtime error in the builders is caught. Skipped headlessly. The dialog methods
use `self` only as a widget parent during construction, so a Tk root stands in."""
import tkinter as tk

import pytest

from tracker import db


@pytest.fixture
def root_with_data(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    jid = db.add_job("Controls Engineer", "Acme", url="u1", source="greenhouse")
    db.update_job(jid, status="applied", follow_up_date="2020-01-01")  # overdue
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    import gui
    gui.theme.apply_theme(root)
    yield root
    root.destroy()


def test_funnel_dialog_builds(root_with_data):
    import gui
    gui.App._show_funnel(root_with_data)   # root stands in for `self` (parent only)
    root_with_data.update_idletasks()


def test_due_dialog_builds(root_with_data):
    import gui
    gui.App._show_due(root_with_data)
    root_with_data.update_idletasks()


def test_contacts_dialog_builds_and_lists(root_with_data):
    import gui
    from tracker import db
    db.add_contact("Jordan Lee", role="Recruiter", company="Acme",
                   email="j@acme.com")
    gui.App._show_contacts(root_with_data)
    root_with_data.update_idletasks()
    assert any(c["name"] == "Jordan Lee" for c in db.list_contacts())


def test_show_privacy_exists_and_callable():
    from ui import help as uihelp
    assert callable(uihelp.show_privacy)
