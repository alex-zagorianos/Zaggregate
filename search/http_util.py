"""Shared HTTP plumbing for the API clients: rate limiting, retry-enabled
sessions, a persistent monthly quota guard, a collision-free cache key, and a
small file cache. Extracted from the three near-identical clients so the
limiter/cache logic lives in exactly one place.
"""
import hashlib
import json
import re
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import CACHE_DIR
from scrape.cache_helpers import read_cache, write_cache


def cache_key(*parts: Any) -> str:
    """Stable hash of all search parameters. Hashing ``repr`` of the normalized
    tuple avoids the slug collisions of the old approach (``"Cincinnati, OH"``
    vs ``"Cincinnati OH"``; ``"controls/automation"`` vs ``"controls automation"``)
    and — critically — includes ``salary_min`` so a filtered search never serves
    an earlier unfiltered cached response.
    """
    normalized = tuple("" if p is None else str(p).strip().lower() for p in parts)
    return hashlib.md5(repr(normalized).encode("utf-8")).hexdigest()


class RateLimiter:
    """Sliding-window limiter, ``max_per_minute`` requests per rolling 60 s.

    Timestamps the *start* of each request (so slow responses don't let the
    window drift), evicts entries older than the window, and loops until a slot
    is actually free. Thread-safe for the parallel search engine.
    """

    def __init__(self, max_per_minute: int, *, quiet: bool = False):
        self.max = max(1, int(max_per_minute))
        self.quiet = quiet
        self._stamps: deque[float] = deque()
        self._lock = threading.Lock()

    def _evict(self, now: float) -> None:
        while self._stamps and now - self._stamps[0] >= 60:
            self._stamps.popleft()

    def acquire(self) -> None:
        with self._lock:
            now = time.time()
            self._evict(now)
            while len(self._stamps) >= self.max:
                sleep_for = 60 - (now - self._stamps[0])
                if sleep_for > 0:
                    if not self.quiet:
                        print(f"  Rate limit: sleeping {sleep_for:.1f}s...")
                    elif sleep_for >= 10:
                        # Even a quiet feed shouldn't look hung for a long cold-cache
                        # wait — emit one ASCII line so the user knows it's alive.
                        print(f"  waiting {sleep_for:.0f}s for rate limit...")
                    time.sleep(sleep_for)
                now = time.time()
                self._evict(now)
            self._stamps.append(time.time())


class MonthlyQuota:
    """Persistent per-calendar-month request counter, e.g. JSearch's 200/month
    free tier. Survives restarts via a small JSON file; resets on month change.
    """

    def __init__(self, path: Path, limit: int):
        self.path = path
        self.limit = limit
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _this_month(self) -> str:
        return datetime.now().strftime("%Y-%m")

    def try_increment(self, n: int = 1) -> bool:
        """Reserve ``n`` requests. Returns False (without incrementing) if that
        would exceed the monthly limit."""
        month = self._this_month()
        with self._lock:
            data = self._load()
            if data.get("month") != month:
                data = {"month": month, "count": 0}
            if data["count"] + n > self.limit:
                return False
            data["count"] += n
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_cache(self.path, data)
            return True

    def decrement(self, n: int = 1) -> None:
        """Refund ``n`` previously-reserved requests (e.g. a failed call that
        never reached the API). Only touches the counter when the stored month
        is the current month; a stale-month file is left untouched."""
        with self._lock:
            data = self._load()
            if data.get("month") != self._this_month():
                return
            data["count"] = max(0, int(data.get("count", 0)) - n)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_cache(self.path, data)

    def remaining(self) -> int:
        data = self._load()
        if data.get("month") != self._this_month():
            return self.limit
        return max(0, self.limit - int(data.get("count", 0)))


def make_session(total_retries: int = 3, backoff: float = 0.5) -> requests.Session:
    """A ``requests.Session`` with automatic backoff retries on transient
    failures (429 + 5xx) so a single network blip doesn't drop a whole page.

    urllib3's ``Retry`` honors a server ``Retry-After`` header, so routing a GET
    through this session (instead of a bare ``requests.get``) makes the app back
    off for exactly as long as the ATS asks on a 429 -- the polite, un-poisoning
    behavior the careers scrapers need.
    """
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ---------------------------------------------------------------------------
# Careers-scrape shared transport: one retry/Retry-After-honoring session reused
# by every ATS scraper, plus a per-ATS-host rate limiter so the 8-worker careers
# pool can't burst a single host into a 429 (which then poisons live boards).
# Both are process-lifetime and thread-safe.
# ---------------------------------------------------------------------------
_careers_session: Optional[requests.Session] = None
_careers_session_lock = threading.Lock()

_careers_host_limiters: dict = {}
_careers_host_limiters_lock = threading.Lock()


def careers_session() -> requests.Session:
    """Shared, lazily-built retry session for the careers scrapers. Its urllib3
    Retry honors 429 + Retry-After, so a throttled ATS is backed off politely
    instead of hammered."""
    global _careers_session
    if _careers_session is None:
        with _careers_session_lock:
            if _careers_session is None:
                _careers_session = make_session()
    return _careers_session


def host_of(url: str) -> str:
    """Lowercased hostname of a URL, '' if unparseable. Used as the rate-limiter
    key so every board on one ATS shares a single per-host window."""
    from urllib.parse import urlsplit
    try:
        host = urlsplit(url).hostname
    except Exception:
        host = None
    return (host or "").lower()


def careers_host_limiter(host: str) -> "RateLimiter":
    """Per-ATS-host RateLimiter (requests/min), created on first use. Rate comes
    from config.CAREERS_HOST_RATE_LIMITS[host] if present, else the global
    CAREERS_HOST_RATE_LIMIT default. Mirrors stealth_fetch._limiter_for."""
    with _careers_host_limiters_lock:
        limiter = _careers_host_limiters.get(host)
        if limiter is None:
            import config
            rate = getattr(config, "CAREERS_HOST_RATE_LIMITS", {}).get(
                host, config.CAREERS_HOST_RATE_LIMIT)
            limiter = RateLimiter(rate, quiet=True)
            _careers_host_limiters[host] = limiter
        return limiter


class FileCache:
    """Thin JSON file cache for one source subdir, using the atomic
    read/write helpers (TTL enforced by ``cache_helpers``)."""

    # Windows-illegal filename characters (a ':' makes NTFS treat the name as an
    # alternate data stream — os.replace then fails with WinError 87), plus the
    # path separators. Mapped to '_' so any client key is a valid filename.
    _UNSAFE_FS = re.compile(r'[<>:"/\\|?*]')

    def __init__(self, subdir: str, cache_dir: Optional[Path] = None):
        self.dir = (cache_dir or CACHE_DIR) / subdir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _file(self, key: str) -> Path:
        return self.dir / f"{self._UNSAFE_FS.sub('_', key)}.json"

    def get(self, key: str) -> Optional[Any]:
        return read_cache(self._file(key))

    def put(self, key: str, data: Any) -> None:
        write_cache(self._file(key), data)


def to_float(value: Any) -> Optional[float]:
    """Coerce an API salary field to float, or None. Guards ``salary_display``
    against APIs that return salaries as strings."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
