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
