"""Persisted UI preferences (light/dark theme choice)."""
import pytest

import config
from ui import settings


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    return tmp_path


def test_default_theme_is_light(isolated):
    assert settings.get_theme() == "light"


def test_set_get_roundtrip(isolated):
    settings.set_theme("dark")
    assert settings.get_theme() == "dark"
    assert (isolated / "ui_settings.json").exists()
    settings.set_theme("light")
    assert settings.get_theme() == "light"


def test_invalid_theme_ignored(isolated):
    settings.set_theme("dark")
    settings.set_theme("neon")          # not a known mode -> no change
    assert settings.get_theme() == "dark"


def test_malformed_file_falls_back(isolated):
    (isolated / "ui_settings.json").write_text("{ not json", encoding="utf-8")
    assert settings.get_theme() == "light"


def test_set_preserves_other_keys(isolated):
    settings.save({"future_pref": 42})
    settings.set_theme("dark")
    data = settings.load()
    assert data["future_pref"] == 42      # we don't clobber unrelated settings
    assert data["theme"] == "dark"
