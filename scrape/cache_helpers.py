import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple, Optional

import requests

from config import (
    CACHE_GC_MAX_AGE_HOURS,
    CACHE_TTL_HOURS,
    FAILED_TTL_HOURS,
    FAILED_TTL_TRANSIENT_HOURS,
)

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
            # No indent: these are machine-only cache blobs (some are multi-MB
            # ATS payloads). Pretty-printing tripled the file size and the write
            # cost for zero human benefit — cache/ is never read by a person.
            json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, cache_file)


def touch_cache(cache_file: Path) -> bool:
    """Refresh a cache file's mtime to now WITHOUT re-serializing its body — used
    on a 304 revalidation, where the server confirmed the cached body is still
    current, so the only thing that needs to change is the TTL clock. Cheaper
    than rewriting a multi-MB ATS payload just to reset one timestamp. Returns
    True if the file existed and was touched, False otherwise."""
    if not cache_file.exists():
        return False
    now = time.time()
    try:
        os.utime(cache_file, (now, now))
        return True
    except OSError:
        return False


def gc_cache_dir(cache_dir: Path, *, max_age_hours: float = CACHE_GC_MAX_AGE_HOURS) -> int:
    """Delete cache files older than ``max_age_hours``. The cache/ tree is
    write-mostly and was never evicted (grew to hundreds of MB); a board that
    hasn't been seen in a week is either dead (already negative-cached) or will
    be re-fetched cheaply on next need. Best-effort, never raises: a file that
    vanishes mid-scan or can't be removed is skipped. Returns the count deleted."""
    if not cache_dir.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for path in cache_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


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


# Status classes for a conditional GET, so a caller can tell a genuinely dead
# board (mark_failed, back off a week) from a throttle/outage blip (serve stale,
# NEVER poison). See scrape/review notes: self-inflicted 429s used to mark live
# boards dead for 168h.
STATUS_OK = "ok"                  # fresh 200 (or 304 with a cached body)
STATUS_TRANSIENT = "transient"    # 429 / 5xx / network error — retry-worthy
STATUS_PERMANENT = "permanent"    # 404 / 410 / other 4xx — board is gone


class FetchResult(NamedTuple):
    """Outcome of a conditional GET. ``body`` is the parsed JSON (or the stale
    cached body on a transient error, or None). ``from_cache`` is True only when
    the body came from a server-confirmed 304. ``status`` is one of STATUS_*."""
    body: Any
    from_cache: bool
    status: str


def _classify_status(code: int) -> str:
    if code == 429 or code >= 500:
        return STATUS_TRANSIENT
    if code >= 400:
        return STATUS_PERMANENT
    return STATUS_OK


def conditional_get(
    url: str,
    cache_path: Path,
    *,
    headers: Optional[dict] = None,
    timeout: Optional[float] = None,
    session: Optional[Any] = None,
) -> FetchResult:
    """Status-aware conditional GET (ETag / Last-Modified). Returns a FetchResult
    so the caller can distinguish failure classes:

      - 200: fresh body cached and returned, status=OK.
      - 304: server confirmed unchanged -> the cached body is returned and its
        TTL clock refreshed via os.utime (NO re-serialization), status=OK.
      - 429 / 5xx: TRANSIENT (throttle/outage). The last-good cached body is
        served if present (never a hard failure), status=TRANSIENT. The caller
        must NOT mark_failed on this -> a live board is never poisoned by a blip.
      - 404 / 410 / other 4xx: PERMANENT. body=None, status=PERMANENT -> the
        caller marks the board failed and backs off, exactly as the pre-migration
        behavior. CRITICAL: a genuinely dead board must never re-serve stale jobs.
      - network exception (no HTTP response): TRANSIENT, stale body served if any.

    Never raises. A server that sends no validators degrades to a plain cached
    GET (body stored, no conditional header next time).
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
        # No HTTP response at all -> transient. Serve stale if we have it.
        return FetchResult(cached_body, False, STATUS_TRANSIENT)

    status_code = getattr(resp, "status_code", 200)
    if status_code == 304:
        if cached_body is not None:
            # Refresh only the TTL clock; the body on disk is already correct.
            touch_cache(cache_path)
            return FetchResult(cached_body, True, STATUS_OK)
        # 304 with nothing cached shouldn't happen, but treat as transient (we
        # sent no validator, so the server can't legitimately 304) rather than
        # poisoning the board.
        return FetchResult(None, False, STATUS_TRANSIENT)

    status_class = _classify_status(status_code)
    if status_class == STATUS_TRANSIENT:
        # 429 / 5xx: the board is up but throttling/erroring right now. Serve the
        # last-good snapshot and DO NOT signal a permanent failure.
        return FetchResult(cached_body, False, STATUS_TRANSIENT)
    if status_class == STATUS_PERMANENT:
        # 404 / 410 / other hard 4xx: board removed/renamed. Never re-serve stale.
        return FetchResult(None, False, STATUS_PERMANENT)

    try:
        body = resp.json()
    except Exception:
        # A 200 that isn't valid JSON is a broken/renamed board, not a blip.
        return FetchResult(None, False, STATUS_PERMANENT)

    resp_headers = getattr(resp, "headers", None) or {}
    get_header = resp_headers.get if hasattr(resp_headers, "get") else (lambda *_a: None)
    new_etag = get_header("ETag")
    new_last_modified = get_header("Last-Modified")
    _write_conditional_entry(cache_path, new_etag, new_last_modified, body)
    return FetchResult(body, False, STATUS_OK)


def conditional_get_json(
    url: str,
    cache_path: Path,
    *,
    headers: Optional[dict] = None,
    timeout: Optional[float] = None,
    session: Optional[Any] = None,
) -> tuple[Any, bool]:
    """Back-compat 2-tuple wrapper over conditional_get(). Returns (payload,
    from_cache). Preserves the S26-r3 regression contract EXACTLY: a permanent
    HTTP error (404/410) returns (None, False) so the caller marks the board
    failed; a transient error (429/5xx/network) returns the stale cached body
    (or None if none) with from_cache=False -- stale-better-than-nothing, and
    the caller decides not to poison. Existing callers that only look at
    ``payload is None`` keep working; new callers use conditional_get() to see
    the status class.
    """
    result = conditional_get(
        url, cache_path, headers=headers, timeout=timeout, session=session
    )
    if result.status == STATUS_PERMANENT:
        return (None, result.from_cache)
    return (result.body, result.from_cache)
