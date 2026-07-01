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


# ── Optional AI API keys (the in-app "Connect your AI" box) ──────────────────────
# Keys live as plaintext files under config.SECRETS_DIR (gitignored, never bundled),
# exactly where the read-side resolvers already look (ranker.api_key reads
# secrets/anthropic_key; serpapi reads secrets/serpapi_key). The clipboard bridge
# stays the default — a key only powers the optional auto-rank + AI resume/cover.
#
# The job-source credentials (the "Connect job sources" box, ui/source_keys.py)
# use the SAME secrets/ mechanism; their on-disk names come from
# config.SOURCE_SECRET_FILES so the filenames live in one place. Provider keys
# here are provider->filename; a source provider whose value is looked up by
# env-then-secret is handled by get/set_api_key below via SOURCE_KEY_ENV.
_KEY_FILES = {"anthropic": "anthropic_key", "serpapi": "serpapi_key"}
_KEY_FILES.update(config.SOURCE_SECRET_FILES)

# The env var that wins over the secret file, per provider key (mirrors the
# resolver precedence in config.resolve_secret). Used by get_api_key so a power
# user's .env still overrides the in-app box for source credentials too.
SOURCE_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "serpapi": "SERPAPI_KEY",
    "adzuna_app_id": "ADZUNA_APP_ID",
    "adzuna_app_key": "ADZUNA_APP_KEY",
    "usajobs_api_key": "USAJOBS_API_KEY",
    "usajobs_email": "USAJOBS_EMAIL",
    "jooble_api_key": "JOOBLE_API_KEY",
    "careerjet_affid": "CAREERJET_AFFID",
    "careeronestop_user_id": "CAREERONESTOP_USER_ID",
    "careeronestop_token": "CAREERONESTOP_TOKEN",
}


def get_api_key(provider: str) -> str:
    """The stored key for a provider (an AI provider like 'anthropic'/'serpapi',
    or a job-source credential like 'adzuna_app_id'/'careeronestop_token'), or ''
    if unset. Prefers the matching env var (so a power user's .env still wins)."""
    import os
    env = SOURCE_KEY_ENV.get(provider)
    if env and os.getenv(env):
        return os.getenv(env)
    name = _KEY_FILES.get(provider)
    return (config.read_secret(name) or "") if name else ""


def has_api_key(provider: str) -> bool:
    return bool(get_api_key(provider))


def set_api_key(provider: str, value: str) -> bool:
    """Persist (or clear, if blank) a provider key to SECRETS_DIR. Returns True on
    success / no-op. Unknown provider returns False."""
    name = _KEY_FILES.get(provider)
    if not name:
        return False
    return config.write_secret(name, value)


def looks_like_key(provider: str, value: str) -> bool:
    """Cheap, offline sanity check for the 'Test key' button (NOT a live API call).
    Anthropic keys start with 'sk-ant-'; otherwise just require some non-space text."""
    v = (value or "").strip()
    if not v:
        return False
    if provider == "anthropic":
        return v.startswith("sk-ant-") and len(v) > 20
    return len(v) >= 8
