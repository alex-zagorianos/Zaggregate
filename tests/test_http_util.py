import time

import pytest

from search.http_util import (
    MonthlyQuota,
    RateLimiter,
    cache_key,
    to_float,
)


# ── cache_key ───────────────────────────────────────────────────────────────

def test_cache_key_includes_salary_min():
    """The original bug: salary_min was omitted, so a filtered search reused an
    earlier unfiltered cached response."""
    k_none = cache_key("adzuna", "controls engineer", "Cincinnati", None, 1)
    k_90k = cache_key("adzuna", "controls engineer", "Cincinnati", 90000, 1)
    assert k_none != k_90k


def test_cache_key_no_slug_collisions():
    # "Cincinnati, OH" vs "Cincinnati OH" collided under the old slug scheme.
    assert cache_key("a", "x", "Cincinnati, OH", None, 1) != cache_key(
        "a", "x", "Cincinnati OH", None, 1
    )
    # "controls/automation" vs "controls automation" likewise.
    assert cache_key("a", "controls/automation", "c", None, 1) != cache_key(
        "a", "controls automation", "c", None, 1
    )


def test_cache_key_stable_and_normalized():
    assert cache_key("a", "Controls Engineer", "Cincinnati", None, 1) == cache_key(
        "a", "controls engineer", "cincinnati", None, 1
    )
    assert isinstance(cache_key("a", 1, None), str)


# ── to_float ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (None, None), ("", None), ("abc", None),
    (90000, 90000.0), ("85000", 85000.0), (85000.5, 85000.5),
])
def test_to_float(value, expected):
    assert to_float(value) == expected


# ── RateLimiter ──────────────────────────────────────────────────────────────

def test_rate_limiter_allows_up_to_max_without_blocking():
    rl = RateLimiter(5, quiet=True)
    start = time.time()
    for _ in range(5):
        rl.acquire()
    assert time.time() - start < 0.5  # no sleep within the window


def test_rate_limiter_evicts_expired(monkeypatch):
    rl = RateLimiter(2, quiet=True)
    t = [1000.0]
    monkeypatch.setattr("search.http_util.time.time", lambda: t[0])
    sleeps = []
    monkeypatch.setattr("search.http_util.time.sleep", lambda s: sleeps.append(s))
    rl.acquire(); rl.acquire()          # window full at t=1000
    t[0] = 1061.0                         # 61s later -> both expired
    rl.acquire()                          # must not sleep
    assert sleeps == []


def test_rate_limiter_blocks_when_full(monkeypatch):
    rl = RateLimiter(2, quiet=True)
    t = [1000.0]
    monkeypatch.setattr("search.http_util.time.time", lambda: t[0])
    slept = []

    def fake_sleep(s):
        slept.append(s)
        t[0] += s  # advance virtual clock past the window

    monkeypatch.setattr("search.http_util.time.sleep", fake_sleep)
    rl.acquire(); rl.acquire()  # full at t=1000
    rl.acquire()                # third must sleep ~60s
    assert slept and abs(slept[0] - 60) < 1


# ── MonthlyQuota ─────────────────────────────────────────────────────────────

def test_monthly_quota_blocks_over_limit(tmp_path):
    q = MonthlyQuota(tmp_path / "usage.json", limit=3)
    assert q.try_increment() is True
    assert q.try_increment() is True
    assert q.try_increment() is True
    assert q.try_increment() is False  # 4th over the cap
    assert q.remaining() == 0


def test_monthly_quota_resets_on_month_change(tmp_path, monkeypatch):
    path = tmp_path / "usage.json"
    q = MonthlyQuota(path, limit=2)
    monkeypatch.setattr(q, "_this_month", lambda: "2026-05")
    assert q.try_increment() and q.try_increment()
    assert q.try_increment() is False
    monkeypatch.setattr(q, "_this_month", lambda: "2026-06")
    assert q.try_increment() is True  # new month -> reset
    assert q.remaining() == 1


def test_monthly_quota_persists(tmp_path):
    path = tmp_path / "usage.json"
    MonthlyQuota(path, limit=5).try_increment(2)
    assert MonthlyQuota(path, limit=5).remaining() == 3  # survives reinstantiation
