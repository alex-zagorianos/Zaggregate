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


def test_guide_goes_deep_on_using_ai():
    blob = " ".join(text for _, text in uihelp.GUIDE)
    headings = [text for tag, text in uihelp.GUIDE if tag in ("h1", "h2")]
    # The Guide now teaches the app is best used WITH AI, in depth.
    assert any("Working with AI" in h for h in headings)
    assert any("Getting the most out of AI" in h for h in headings)
    for phrase in ["Ask AI to rank these", "Paste AI ranking", "round-trip",
                   "API key", "Anything else", "tailored", "mirrors what you tell"]:
        assert phrase in blob, phrase


def test_guide_goes_deep_on_source_setup():
    blob = " ".join(text for _, text in uihelp.GUIDE)
    headings = [text for tag, text in uihelp.GUIDE if tag in ("h1", "h2")]
    # The Guide must teach the source-key setup and local-employer seeding —
    # live testing (2026-07-01) showed the keyless out-of-box tier contributed
    # ~1% of inbox rows; the free keys + the registry carried everything else.
    assert any("Set up your sources" in h for h in headings)
    for phrase in ["Connect job sources", "Adzuna", "CareerOneStop",
                   "Add Companies", "Name | link", "fails verification",
                   "daily updates"]:
        assert phrase in blob, phrase
    # The AI-assisted employer-list flow is documented (manual precursor of the
    # held "Seed My Area" plan — brain/plan-2026-07-01-ai-assisted-setup-seeding.md).
    assert "largest employers" in blob


def test_guide_add_companies_copy_is_truthful_about_verification():
    # P0-6: the old copy claimed unverified boards "simply fail verification —
    # nothing bad can sneak in", but every parsed line was saved and re-scraped
    # forever. The corrected copy must not overpromise, and must tell the user
    # what actually happens to a board that fails the live probe.
    blob = " ".join(text for _, text in uihelp.GUIDE)
    assert "nothing bad can sneak in" not in blob      # the false claim is gone
    # The copy now describes the real behavior: unverified boards are kept out
    # of searches until they verify.
    assert "unverified" in blob
    assert "fails verification" in blob


def test_ai_help_dialog_callable():
    assert callable(uihelp.show_ai_help)


def test_ai_help_does_not_overpromise_auto_ranking():
    blob = " ".join(text for _, text in uihelp.GUIDE)
    # The GUI / daily run never auto-AI-rank; the in-app way is the free bridge.
    assert "ranks the inbox automatically" not in blob
    assert "needs no key" in blob                  # ranking is free
    # The API key is correctly tied to writing applications, not ranking.
    assert "needs an AI API key" in blob


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
