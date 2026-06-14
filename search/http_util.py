"""Shared HTTP plumbing for the API clients: rate limiting, retry-enabled
sessions, a persistent monthly quota guard, a collision-free cache key, and a
small file cache. Extracted from the three near-identical clients so the
limiter/cache logic lives in exactly one place.
"""
import hashlib
import json
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

    def remaining(self) -> int:
        data = self._load()
        if data.get("month") != self._this_month():
            return self.limit
        return max(0, self.limit - int(data.get("count", 0)))


def make_session(total_retries: int = 3, backoff: float = 0.5) -> requests.Session:
    """A ``requests.Session`` with automatic backoff retries on transient
    failures (429 + 5xx) so a single network blip doesn't drop a whole page."""
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class FileCache:
    """Thin JSON file cache for one source subdir, using the atomic
    read/write helpers (TTL enforced by ``cache_helpers``)."""

    def __init__(self, subdir: str, cache_dir: Optional[Path] = None):
        self.dir = (cache_dir or CACHE_DIR) / subdir
        self.dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Optional[Any]:
        return read_cache(self.dir / f"{key}.json")

    def put(self, key: str, data: Any) -> None:
        write_cache(self.dir / f"{key}.json", data)


def to_float(value: Any) -> Optional[float]:
    """Coerce an API salary field to float, or None. Guards ``salary_display``
    against APIs that return salaries as strings."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
