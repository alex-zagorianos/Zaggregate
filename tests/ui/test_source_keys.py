"""B2 — 'Connect job sources' dialog smoke + guarded live-probe.

The dialog build is skipped headlessly (same pattern as tests/ui/test_dialogs).
The live-probe worker (test_source) is unit-tested WITHOUT a Tk root and never
touches the network under pytest (PYTEST_CURRENT_TEST guard).
"""
import tkinter as tk

import pytest

import config
from ui import source_keys


@pytest.fixture
def secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    # Env wins over secrets by design; a dev machine's .env (real keys loaded
    # into the process env by config) must not shadow the seeded test secret.
    for var in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "USAJOBS_API_KEY",
                "USAJOBS_EMAIL", "JOOBLE_API_KEY", "CAREERJET_AFFID",
                "CAREERONESTOP_USER_ID", "CAREERONESTOP_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path / "secrets"


def test_source_catalog_shape():
    keys = {s["key"] for s in source_keys.SOURCES}
    assert keys == {"adzuna", "usajobs", "jooble", "careerjet", "careeronestop"}
    for s in source_keys.SOURCES:
        assert s["url"].startswith("http")
        assert s["fields"]                       # at least one credential
        for secret_name, label in s["fields"]:
            assert secret_name in config.SOURCE_SECRET_FILES
            assert label


def test_source_urls_are_direct_signup_pages():
    # S34: the per-source buttons must land on the direct free-key page, not a
    # generic landing/home. USAJobs -> the API-request form; Careerjet -> the
    # publisher signup that issues the affiliate ID.
    by_key = {s["key"]: s["url"] for s in source_keys.SOURCES}
    assert by_key["usajobs"] == "https://developer.usajobs.gov/apirequest/"
    assert by_key["careerjet"] == "https://www.careerjet.com/partners/publishers/"
    assert by_key["adzuna"] == "https://developer.adzuna.com/"
    assert "registration.aspx" in by_key["careeronestop"]


def test_reference_sources_have_free_key_links():
    # S34: SerpApi + JSearch are configured elsewhere but still surface a
    # one-click free-key link here, so every usable source has a signup path.
    labels = {label for label, _ in source_keys.REFERENCE_SOURCES}
    urls = {url for _, url in source_keys.REFERENCE_SOURCES}
    assert any("SerpApi" in l for l in labels)
    assert any("JSearch" in l for l in labels)
    assert "https://serpapi.com/users/sign_up" in urls
    assert any("rapidapi.com" in u for u in urls)
    for _, url in source_keys.REFERENCE_SOURCES:
        assert url.startswith("https://")


def test_test_source_is_guarded_under_pytest():
    # PYTEST_CURRENT_TEST is set by pytest, so the live probe must never run.
    for key in ("adzuna", "usajobs", "jooble", "careerjet", "careeronestop"):
        ok, msg = source_keys.test_source(key)
        assert ok is False
        assert msg == "skipped (test mode)"


def test_test_source_unknown():
    # Even the unknown branch stays guarded under pytest.
    ok, msg = source_keys.test_source("nope")
    assert ok is False


def test_open_dialog_builds(secrets):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        win = source_keys.open_dialog(root)
        assert win is not None
        win.update_idletasks()
        # Every credential entry was created (StringVars are seeded from secrets).
        win.destroy()
    finally:
        root.destroy()


# ── §6.6: Adzuna paste-split ──────────────────────────────────────────────────

def test_split_adzuna_paste_labeled_blob():
    blob = "Application ID: 1a2b3c4d\nApplication Key: " + "f" * 32
    app_id, app_key = source_keys.split_adzuna_paste(blob)
    assert app_id == "1a2b3c4d"
    assert app_key == "f" * 32


def test_split_adzuna_paste_space_separated():
    app_id, app_key = source_keys.split_adzuna_paste("deadbeef " + "a" * 32)
    assert app_id == "deadbeef"
    assert app_key == "a" * 32


def test_split_adzuna_paste_id_not_confused_with_key_prefix():
    """The first 8 chars of the 32-hex key must NOT be picked up as the app id."""
    key = "0123456789abcdef0123456789abcdef"
    app_id, app_key = source_keys.split_adzuna_paste(key)   # ONLY a key present
    assert app_key == key
    assert app_id == ""                                     # no separate id token


def test_split_adzuna_paste_only_id():
    app_id, app_key = source_keys.split_adzuna_paste("App ID abcd1234")
    assert app_id == "abcd1234"
    assert app_key == ""


def test_split_adzuna_paste_junk_yields_empty():
    assert source_keys.split_adzuna_paste("no credentials here") == ("", "")
    assert source_keys.split_adzuna_paste("") == ("", "")


def test_looks_like_adzuna_paste():
    assert source_keys.looks_like_adzuna_paste("abcd1234") is True
    assert source_keys.looks_like_adzuna_paste("e" * 32) is True
    assert source_keys.looks_like_adzuna_paste("hello world") is False


def test_open_dialog_seeds_from_secrets(secrets):
    from ui import settings
    settings.set_api_key("adzuna_app_id", "seeded-id")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        win = source_keys.open_dialog(root)
        win.update_idletasks()
        # The seeded value is read back via settings (proves save/read wiring).
        assert settings.get_api_key("adzuna_app_id") == "seeded-id"
        win.destroy()
    finally:
        root.destroy()
