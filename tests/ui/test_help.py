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
    # And a brand-new user must learn how the Inbox behaves on day one — it now
    # shows a SAMPLE feed first (§6.1), replaced by real jobs on the first update.
    assert "SAMPLE" in blob and "Update my Inbox now" in blob


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


def test_guide_aligns_with_wizard_keys_step_and_silent_zero_line():
    """The Guide must reflect the new flow: the wizard's keys step and the Inbox
    'N sources skipped (no key)' surfacing (so the copy matches what users see)."""
    blob = " ".join(text for _, text in uihelp.GUIDE)
    # Names the new wizard keys step.
    assert "Connect your best free sources" in blob
    # Explains the Inbox skipped-sources cue (the silent-zero fix).
    assert "sources skipped (no key)" in blob


def test_guide_leads_with_own_your_data_and_no_auto_apply(tmp_path):
    """QW-7 positioning: the Guide must carry the own-your-data + assisted-not-auto
    story with the researched stats, framed exactly as evidenced (no overclaim)."""
    headings = [text for tag, text in uihelp.GUIDE if tag in ("h1", "h2")]
    assert any("Why Zaggregate" in h for h in headings)
    blob = " ".join(text for _, text in uihelp.GUIDE)
    # The two headline stats, stated as the research doc evidences them.
    assert "90%" in blob                       # data-selling prevalence
    assert "0.01%" in blob and "4" in blob     # auto-apply vs tailored success
    # The core posture words.
    for phrase in ("account", "sold", "auto-apply", "you always click submit",
                   "reach"):
        assert phrase in blob, phrase


def test_guide_field_copy_names_the_real_wizard_step_not_a_dead_label():
    # The wizard has no "What kind of work?" step; the field control lives in the
    # "What jobs are you looking for?" step as "Your field / industry". The Guide
    # copy must reference what the user actually sees.
    blob = " ".join(text for _, text in uihelp.GUIDE)
    assert "What kind of work?" not in blob
    assert "What jobs are you looking for?" in blob
    assert "Your field / industry" in blob


def test_guide_lists_the_board_tab():
    # The Board (Kanban) notebook tab must appear in the "What each tab does"
    # section (it was previously omitted).
    headings = [text for tag, text in uihelp.GUIDE if tag == "h2"]
    assert "Board" in headings
    blob = " ".join(text for _, text in uihelp.GUIDE)
    assert "one column per" in blob and "Move" in blob


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
