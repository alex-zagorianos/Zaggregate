"""Shared base for the keyless single-feed clients.

remoteok / remotive / jobicy / himalayas / themuse / hn all share the same
boilerplate: a polite User-Agent, a per-source ``FileCache`` subdir, a retrying
``make_session``, a ``RateLimiter``, an HTML stripper, and the get-cache /
fetch / put-cache dance. That boilerplate lived copy-pasted in six files; it
now lives here exactly once.

The four keyed-API clients (adzuna/jsearch/usajobs/etc.) are NOT in scope —
they carry API keys and a monthly quota and keep their own ``__init__``.

Subclasses set a ``cache_subdir`` and a ``rate_limit`` (or override ``__init__``
to read them from ``config``), then call ``self._cached(key, fetch)`` to get the
read-cache / fetch / write-cache template for free.
"""
import json
import re
from pathlib import Path
from typing import Any, Callable, Optional

import applog
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, make_session

# One HTML-tag stripper shared by every feed (was duplicated as _TAG_RE in each).
_TAG_RE = re.compile(r"<[^>]+>")

# Cap on recursion depth while walking a cached payload for 'title' fields —
# real feed JSON is a few levels deep (dict-of-list-of-dicts at most); the cap
# just stops a pathological/circular-looking structure from spinning.
_TITLE_WALK_MAX_DEPTH = 6


def _walk_titles(obj: Any, out: list[str], depth: int = 0) -> None:
    """Recursively pull any string 'title' field out of a JSON-shaped payload,
    format-agnostic across feeds (list-of-dicts, dict-of-lists, either nested
    inside the other). Used by ``cached_titles()`` so corpus mining doesn't
    need to know each feed's private cache shape."""
    if depth > _TITLE_WALK_MAX_DEPTH:
        return
    if isinstance(obj, dict):
        t = obj.get("title")
        if isinstance(t, str) and t.strip():
            out.append(t.strip())
        for v in obj.values():
            _walk_titles(v, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _walk_titles(item, out, depth + 1)


class SingleFeedClient(JobAPIClient):
    """Base for the keyless feed clients. Provides the shared __init__
    (User-Agent, FileCache, make_session, RateLimiter), an HTML stripper, and a
    cache-aware fetch template."""

    #: Per-source User-Agent. Override only if a source needs a different one.
    user_agent = "JobSearchTool/1.0 (personal use)"
    #: FileCache subdir name; subclasses MUST set this.
    cache_subdir: str = ""
    #: RateLimiter ceiling (requests/minute); subclasses MUST set this.
    rate_limit: int = 1

    def __init__(self, cache_dir: Optional[Path] = None, cache_enabled: bool = True):
        self.cache = FileCache(self.cache_subdir, cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.session.headers["User-Agent"] = self.user_agent
        self.limiter = RateLimiter(self.rate_limit, quiet=True)

    @staticmethod
    def strip_html(text: str) -> str:
        """Replace HTML tags with spaces. Shared by every feed's parse step."""
        return _TAG_RE.sub(" ", text or "")

    def _cached(self, key: str, fetch: Callable[[], Any]) -> Any:
        """Read-cache / fetch / write-cache template.

        Returns the cached value for ``key`` if caching is on and a fresh entry
        exists; otherwise calls ``fetch()`` (which does the rate-limited HTTP
        work and returns the data dict), stores it, and returns it.

        If ``fetch()`` RAISES (a transport error, or a feed parser like
        ``_parse_feed`` signaling "this response was unparseable" rather than
        "a genuinely empty feed"), the failure is logged via applog and the
        cache is NOT written for this key -- a transient feed-format hiccup
        must not silence the source for the full cache TTL (S35 finding #5).
        The exception still propagates so the caller's per-keyword error
        handling (search_engine._run_client) sees it exactly as before.
        """
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        try:
            data = fetch()
        except Exception as e:
            applog.get_logger("sources").warning(
                f"  [{self.cache_subdir}] fetch/parse failed for {key!r} — "
                f"{type(e).__name__}: {e} (not cached; will retry next run)")
            raise
        if self.cache_enabled:
            self.cache.put(key, data)
        return data

    def cached_titles(self) -> list[str]:
        """Best-effort: return job titles found in THIS source's on-disk cache,
        format-agnostic. Enumerates cached payloads and pulls any 'title'-like
        string field (dicts with a 'title' key, nested lists of such dicts).
        Returns [] when the cache is empty/unreadable — never raises. Corpus
        mining uses this as a secondary signal; a source that stores an opaque
        shape simply contributes nothing.

        FileCache itself has no key-enumeration API, so this reads the cache
        subdir's *.json files directly (same layout FileCache._file() writes)
        rather than adding one — TTL/freshness doesn't matter for mining, a
        title from a week-old cache is still a real candidate title.
        """
        titles: list[str] = []
        try:
            cache_dir = self.cache.dir
            if not cache_dir.exists():
                return []
            for path in cache_dir.glob("*.json"):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict) and data.get("_failed") is True:
                    continue  # negative-cache marker, not a payload
                _walk_titles(data, titles)
        except Exception:
            return []
        return titles
