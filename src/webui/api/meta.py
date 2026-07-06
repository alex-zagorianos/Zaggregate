"""Product meta routes (B1 beta buildout): version, update check, feedback target.

Three small routes that power the Settings menu's "Check for updates" and
"Send feedback" items:

* ``GET  /api/meta/version``          -> ``{ok, version}`` (config.APP_VERSION).
* ``POST /api/meta/update-check``     -> ``{ok, current, latest, url, newer}``
  [origin-gated]. Queries the public GitHub releases API for
  ``config.UPDATE_REPO`` (stdlib urllib, 5s timeout) and compares the latest
  release tag to APP_VERSION. Result is cached to a file under the userdata cache
  dir for 24h. ``latest`` is ``null`` GRACEFULLY on ANY failure (offline, private
  repo 404, no releases yet, malformed JSON) — a network failure is NEVER an
  ``{ok:false}`` error envelope, so the UI can quietly say "couldn't check" and a
  cross-site page can't distinguish states it shouldn't.
* ``GET  /api/meta/feedback-target``  -> ``{ok, email, subject}``. The mailto:
  is built CLIENT-side from these fields (opens the user's own mail app —
  nothing is sent from the app itself, matching the local/no-telemetry stance).

No telemetry: the update check is the only outbound call here, it is user-
triggered, and it sends nothing but the standard GET (no identifiers). The
report-a-problem zip is a tk-only helper (help_core / applog); we do NOT port it
to the web layer — feedback is a plain mailto.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from flask import Blueprint, jsonify

import config
from ..security import require_local_origin

meta_bp = Blueprint("webui_meta", __name__)

# GitHub's public latest-release endpoint (no auth for a public repo).
_GITHUB_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
_UPDATE_TIMEOUT_S = 5
_CACHE_TTL_S = 24 * 60 * 60  # 24h
_CACHE_NAME = "update_check.json"


def _cache_path() -> Path:
    """The 24h update-check cache file under the userdata cache dir. Read lazily
    (config.CACHE_DIR, gitignored) so a test repointing it is honored."""
    return config.CACHE_DIR / _CACHE_NAME


def _parse_version(tag: str) -> tuple[int, ...]:
    """A tolerant semver-ish parse: strip a leading 'v', keep the leading run of
    dot-separated integers ('v1.2.3' -> (1,2,3); '1.2.3-beta' -> (1,2,3)). A tag
    with no leading numeric component yields () so it never compares as 'newer'."""
    s = (tag or "").strip().lstrip("vV")
    parts: list[int] = []
    for chunk in s.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        if not num:
            break
        parts.append(int(num))
    return tuple(parts)


def _is_newer(latest: str, current: str) -> bool:
    """True iff ``latest`` parses to a strictly greater version tuple than
    ``current``. Unparseable/absent tags -> False (never nag on garbage)."""
    lv = _parse_version(latest)
    cv = _parse_version(current)
    if not lv:
        return False
    return lv > cv


def _read_cache() -> dict | None:
    """The cached update-check result if present and < 24h old, else None."""
    try:
        raw = _cache_path().read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    ts = data.get("_cached_at")
    if not isinstance(ts, (int, float)):
        return None
    if (time.time() - ts) > _CACHE_TTL_S:
        return None
    payload = data.get("payload")
    return payload if isinstance(payload, dict) else None


def _write_cache(payload: dict) -> None:
    """Best-effort write of the update-check payload + a timestamp. Never raises —
    a cache-write failure must not turn a successful check into an error."""
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"_cached_at": time.time(), "payload": payload}),
            encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _fetch_latest_tag() -> str | None:
    """The latest release tag from GitHub for config.UPDATE_REPO, or None on ANY
    failure (offline, 404 private/no-releases, non-JSON, missing tag_name). Never
    raises — the caller treats None as 'couldn't determine', not an error."""
    url = _GITHUB_LATEST.format(repo=config.UPDATE_REPO)
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github+json",
                          "User-Agent": "Zaggregate-update-check"})
        with urllib.request.urlopen(req, timeout=_UPDATE_TIMEOUT_S) as resp:
            body = resp.read()
        data = json.loads(body)
    except Exception:
        # urllib raises a zoo of exception types (URLError, HTTPError, socket
        # timeout, ssl errors, JSON errors); ALL of them mean "couldn't check".
        return None
    if not isinstance(data, dict):
        return None
    tag = data.get("tag_name") or data.get("name")
    return str(tag) if tag else None


@meta_bp.get("/meta/version")
def meta_version():
    """The running app version (config.APP_VERSION). Pure read."""
    return jsonify({"ok": True, "version": config.APP_VERSION})


@meta_bp.post("/meta/update-check")
@require_local_origin
def meta_update_check():
    """Check GitHub for a newer release. Returns
    ``{ok, current, latest, url, newer}``; ``latest`` is null (and ``newer``
    false) whenever the check couldn't complete for ANY reason — a network
    failure is deliberately NOT an ``{ok:false}`` envelope. Cached 24h."""
    current = config.APP_VERSION
    releases_url = f"https://github.com/{config.UPDATE_REPO}/releases"

    cached = _read_cache()
    if cached is not None:
        return jsonify({"ok": True, **cached})

    latest = _fetch_latest_tag()
    payload = {
        "current": current,
        "latest": latest,
        "url": releases_url,
        "newer": bool(latest) and _is_newer(latest, current),
    }
    # Only cache a conclusive result (a real latest tag). A transient failure
    # (latest=None) is NOT cached, so the next click re-probes instead of being
    # stuck on "couldn't check" for 24h.
    if latest is not None:
        _write_cache(payload)
    return jsonify({"ok": True, **payload})


@meta_bp.get("/meta/feedback-target")
def meta_feedback_target():
    """The mailto target for "Send feedback": ``{ok, email, subject}``. The
    subject carries the version so an inbound report is pre-tagged. The client
    builds the mailto: (opening the user's own mail app) — nothing is sent from
    here. Pure read."""
    return jsonify({
        "ok": True,
        "email": config.FEEDBACK_EMAIL,
        "subject": f"Zaggregate feedback (v{config.APP_VERSION})",
    })
