"""Headless-safe smoke tests for the AI-setup GUI surfaces (§6.3 / §6.7).

Builds AiSetupDialog and AddCompaniesDialog under a Tk root (skips when no
display) so a construction-time error in the widgets is caught. The parse/apply
logic itself is covered in tests/ui/test_ai_setup.py.
"""
import tkinter as tk

import pytest

import config
import workspace


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "PREFERENCES_JSON", tmp_path / "preferences.json")
    monkeypatch.setattr(config, "PREFERENCES_MD", tmp_path / "preferences.md")
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


def test_ai_setup_dialog_builds_and_shows_prompt(root):
    import gui
    dlg = gui.AiSetupDialog(root)
    root.update_idletasks()
    # The prompt box is populated with the documented block and is read-only.
    text = dlg._prompt_box.get("1.0", "end-1c")
    assert "```json" in text and "preferences_md" in text
    assert str(dlg._prompt_box.cget("state")) == "disabled"
    dlg.destroy()


def test_ai_setup_dialog_apply_empty_reply_is_gentle(root):
    import gui
    dlg = gui.AiSetupDialog(root)
    root.update_idletasks()
    dlg._apply()                        # nothing pasted -> status hint, no crash
    assert "paste" in str(dlg._status.cget("text")).lower()
    dlg.destroy()


def test_add_companies_dialog_has_seed_prompt_button(root, monkeypatch):
    import gui
    copied = {}
    monkeypatch.setattr(gui, "to_clipboard",
                        lambda t: copied.setdefault("text", t) is None or True)
    dlg = gui.AddCompaniesDialog(root, default_industry="nursing",
                                 default_metro="Boise, ID")
    root.update_idletasks()
    dlg._copy_seed_prompt()             # exercises build_seed_prompt + clipboard
    assert "careers" in copied["text"].lower()
    assert "nursing" in copied["text"] and "Boise" in copied["text"]
    dlg.destroy()
