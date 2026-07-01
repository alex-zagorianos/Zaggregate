import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

from config import CACHE_TTL_HOURS, FAILED_TTL_HOURS

# Characters that are illegal in Windows filenames (": " breaks Workday slugs
# like "cat:5:CaterpillarCareers" -> [Errno 22] Invalid argument).
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*,\s]+')


def read_cache(cache_file: Path, ttl_hours: float = CACHE_TTL_HOURS) -> Optional[Any]:
    if not cache_file.exists():
        return None
    age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
    if age > timedelta(hours=ttl_hours):
        return None
    with open(cache_file, "r", encoding="utf-8") as f:
        content = f.read()
    if cache_file.suffix == ".json":
        return json.loads(content)
    return content


def read_failed(failed_file: Path) -> Optional[Any]:
    """Read a negative-cache "_FAILED" marker on the longer FAILED_TTL_HOURS
    window. Use with is_failed() so a known-dead URL is skipped for a week
    instead of being re-probed (at full request timeout) on every daily run."""
    return read_cache(failed_file, ttl_hours=FAILED_TTL_HOURS)


def write_cache(cache_file: Path, data: Any) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_suffix(cache_file.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, indent=2)
    os.replace(tmp, cache_file)


def slug_safe(text: str) -> str:
    return _UNSAFE_CHARS.sub("_", text.lower()).strip("_")


def mark_failed(cache_file: Path) -> None:
    """Negative-cache a fetch failure. Dead slugs (404/timeout) were retried
    for every keyword in a run — ~10 doomed requests per dead company per
    day. The marker makes it one attempt per TTL window."""
    write_cache(cache_file, {"_failed": True})


def is_failed(cached) -> bool:
    return isinstance(cached, dict) and cached.get("_failed") is True


# ---------------------------------------------------------------------------
# HTTP conditional GET (ETag / Last-Modified) — free-efficiency: on a
# same-content daily run, an ATS board answers 304 Not Modified instead of
# re-sending the full JSON payload. Wraps the cached body alongside its
# validators; the wrapper is namespaced with _HTTP_CACHE_MARKER so a bare
# read_cache() hit on an entry written by write_cache() elsewhere (the plain,
# pre-migration format) is never mistaken for one of these entries.
# ---------------------------------------------------------------------------
_HTTP_CACHE_MARKER = "_http_cache"


def _read_json_file(path: Path) -> Optional[Any]:
    """Read a JSON cache file ignoring its TTL/age — conditional GET revalidates
    freshness with the server itself, so an "expired" entry is still a valid
    candidate to send as If-None-Match/If-Modified-Since."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    except (OSError, json.JSONDecodeError):
        return None


def _read_conditional_entry(cache_path: Path) -> Optional[dict]:
    """Return {"etag", "last_modified", "body"} regardless of age, or None if
    there's nothing usable on disk. Understands three shapes:
      - a wrapped conditional-cache entry written by this module,
      - a "_failed" negative-cache marker (not usable body data), and
      - a legacy plain body (pre-migration write_cache() dump: the raw
        greenhouse/lever JSON with no validator) — still returned as a body
        with no etag so a stale-body network-error fallback still works."""
    raw = _read_json_file(cache_path)
    if raw is None:
        return None
    if isinstance(raw, dict) and raw.get(_HTTP_CACHE_MARKER) is True:
        return {
            "etag": raw.get("etag"),
            "last_modified": raw.get("last_modified"),
            "body": raw.get("body"),
        }
    if isinstance(raw, dict) and raw.get("_failed") is True:
        return None
    return {"etag": None, "last_modified": None, "body": raw}


def _write_conditional_entry(cache_path: Path, etag: Optional[str],
                             last_modified: Optional[str], body: Any) -> None:
    write_cache(cache_path, {
        _HTTP_CACHE_MARKER: True,
        "etag": etag,
        "last_modified": last_modified,
        "body": body,
        "ts": datetime.now().isoformat(),
    })


def http_cache_body(entry: Any) -> Any:
    """Unwrap a cache entry that may be either the new conditional-GET wrapper
    or a legacy plain body, so callers' TTL-freshness fast path (a bare
    read_cache() call) keeps working across the migration."""
    if isinstance(entry, dict) and entry.get(_HTTP_CACHE_MARKER) is True:
        return entry.get("body")
    return entry


def conditional_get_json(
    url: str,
    cache_path: Path,
    *,
    headers: Optional[dict] = None,
    timeout: Optional[float] = None,
    session: Optional[Any] = None,
) -> tuple[Any, bool]:
    """GET a JSON endpoint using HTTP conditional-GET validators (ETag /
    Last-Modified) so an unchanged ATS board is answered with a cheap 304
    instead of a full re-download. Returns (payload, from_cache):
      - payload is the parsed JSON body (dict/list), or None if nothing is
        available (no cache and the request failed).
      - from_cache is True only for a 304 (server-confirmed unchanged; the
        cached body is returned unparsed-from-network).

    Backward compatible: a server that sends no ETag/Last-Modified degrades to
    a normal cached GET (body stored, no conditional header sent next time).
    On a network error, the last-good cached body is returned if one exists
    (stale-better-than-nothing). Never raises.
    """
    getter = session.get if session is not None else requests.get
    req_headers: dict = dict(headers or {})

    entry = _read_conditional_entry(cache_path)
    cached_body = entry.get("body") if entry else None
    if entry:
        if entry.get("etag"):
            req_headers.setdefault("If-None-Match", entry["etag"])
        if entry.get("last_modified"):
            req_headers.setdefault("If-Modified-Since", entry["last_modified"])

    try:
        resp = getter(url, headers=req_headers or None, timeout=timeout)
    except Exception:
        return (cached_body, False)

    status = getattr(resp, "status_code", 200)
    if status == 304:
        if cached_body is not None:
            _write_conditional_entry(
                cache_path,
                entry.get("etag") if entry else None,
                entry.get("last_modified") if entry else None,
                cached_body,
            )
            return (cached_body, True)
        return (None, False)

    try:
        resp.raise_for_status()
    except Exception:
        # The server ANSWERED with a 4xx/5xx (board removed/renamed/broken) — this
        # is a real failure, not a transient network blip. Signal it (None) so the
        # caller marks the board failed and backs off, exactly as before the
        # conditional-GET migration; do NOT re-serve a stale snapshot as if live
        # (that would resurrect a dead board's jobs forever).
        return (None, False)
    try:
        body = resp.json()
    except Exception:
        return (None, False)

    resp_headers = getattr(resp, "headers", None) or {}
    get_header = resp_headers.get if hasattr(resp_headers, "get") else (lambda *_a: None)
    new_etag = get_header("ETag")
    new_last_modified = get_header("Last-Modified")
    _write_conditional_entry(cache_path, new_etag, new_last_modified, body)
    return (body, False)
