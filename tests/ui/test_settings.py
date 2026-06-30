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


def test_default_location_mode_is_local_plus_remote(isolated):
    assert settings.get_location_mode() == "Local + remote"


def test_location_mode_roundtrip(isolated):
    settings.set_location_mode("Local only")
    assert settings.get_location_mode() == "Local only"
    settings.set_location_mode("All locations")
    assert settings.get_location_mode() == "All locations"


def test_invalid_location_mode_ignored(isolated):
    settings.set_location_mode("Local only")
    settings.set_location_mode("Mars")        # unknown -> no change
    assert settings.get_location_mode() == "Local only"


def test_location_mode_and_theme_coexist(isolated):
    settings.set_theme("dark")
    settings.set_location_mode("Local only")
    assert settings.get_theme() == "dark"      # neither setting clobbers the other
    assert settings.get_location_mode() == "Local only"
