"""Tiny persisted UI preferences (currently just the light/dark theme choice),
stored as JSON in the user's data folder so it survives restarts. Best-effort:
a read-only or missing file never crashes the app — it just falls back to
defaults, exactly like the .onboarded marker."""
import json
from pathlib import Path

import config
from geo.filter import LOCATION_MODES, DEFAULT_LOCATION_MODE

_FILENAME = "ui_settings.json"
_VALID_THEMES = ("light", "dark")
_DEFAULT_THEME = "light"


def _path() -> Path:
    return Path(config.USER_DATA_DIR) / _FILENAME


def load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save(data: dict) -> None:
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def get_theme() -> str:
    """The saved theme, or 'light' if unset/invalid."""
    theme = load().get("theme")
    return theme if theme in _VALID_THEMES else _DEFAULT_THEME


def set_theme(mode: str) -> None:
    """Persist the theme choice (ignored if not a known mode)."""
    if mode not in _VALID_THEMES:
        return
    data = load()
    data["theme"] = mode
    save(data)


def get_location_mode() -> str:
    """The saved Inbox Location view-filter mode, or the local-focused default."""
    mode = load().get("location_mode")
    return mode if mode in LOCATION_MODES else DEFAULT_LOCATION_MODE


def set_location_mode(mode: str) -> None:
    """Persist the Inbox Location view-filter mode (ignored if not a known mode)."""
    if mode not in LOCATION_MODES:
        return
    data = load()
    data["location_mode"] = mode
    save(data)
