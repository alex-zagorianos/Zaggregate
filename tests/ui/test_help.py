"""In-app Guide content + Help actions."""
import pytest

import config
from ui import help as uihelp


def test_guide_has_structure_and_key_phrases():
    tags = {tag for tag, _ in uihelp.GUIDE}
    assert {"h1", "h2", "body"} <= tags
    blob = " ".join(text for _, text in uihelp.GUIDE)
    # The walkthrough names the core workflow in plain English.
    for phrase in ["Inbox", "Apply Queue", "Track", "Ask AI to rank",
                   "data folder"]:
        assert phrase in blob, phrase


def test_guide_explains_fit_vs_score_and_day_one():
    blob = " ".join(text for _, text in uihelp.GUIDE)
    # Score vs Fit is the UI's most confusing pair — the Guide must distinguish them.
    assert "Score" in blob and "Fit grade" in blob
    # And a brand-new user must learn the Inbox starts empty on day one.
    assert "starts empty" in blob


def test_open_data_folder_targets_user_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    opened = {}
    monkeypatch.setattr(uihelp, "_open_path", lambda p: opened.setdefault("p", p))
    uihelp.open_data_folder()
    assert opened["p"] == tmp_path
    assert tmp_path.exists()


def test_quick_start_and_about_text_exist():
    # The popup helpers are thin wrappers; just ensure they're callable objects
    # with the expected names (no display needed to assert presence).
    assert callable(uihelp.show_quick_start)
    assert callable(uihelp.show_tabs_help)
    assert callable(uihelp.show_about)
