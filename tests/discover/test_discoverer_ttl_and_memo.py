"""S35 finding #25 (inefficiency): Brave company-discovery re-fired all 5 ATS
site: queries per keyword EVERY DAY because the on-disk cache TTL
(CACHE_TTL_HOURS=24) sits right at daily_run's ~24h schedule boundary -- in
practice the cache was stale by the next run. Fixed two ways:

1. A dedicated, much longer DISCOVERY_CACHE_TTL_HOURS (7 days, config.py) used
   ONLY for the discovery cache read -- cache-miss (fetch + write) behavior is
   otherwise identical.
2. A process-local in-run memo (_RUN_QUERY_MEMO) so the SAME (ats_site,
   keyword) pair queried twice within one run/process reuses the first
   result with zero extra disk I/O.
"""
import time

import applog
import scrape.discoverer as D
from config import DISCOVERY_CACHE_TTL_HOURS


def _payload(slugs):
    return {"web": {"results": [
        {"url": f"https://boards.greenhouse.io/{s}"} for s in slugs
    ]}}


def _setup(monkeypatch):
    monkeypatch.setattr(D, "BRAVE_SEARCH_API_KEY", "a-real-key")
    applog.reset_run_warnings()
    D.reset_run_memo()


def test_discovery_ttl_constant_is_much_longer_than_default_24h():
    assert DISCOVERY_CACHE_TTL_HOURS >= 168        # >= 7 days
    assert DISCOVERY_CACHE_TTL_HOURS > 24           # strictly longer than the generic TTL


def test_cache_at_25h_old_is_still_a_hit_not_a_live_refetch(tmp_path, monkeypatch):
    # A cache entry aged past the OLD 24h TTL (but well inside the new 7-day
    # one) must NOT trigger a live Brave call -- this is the exact daily-run
    # boundary bug: yesterday's cache was already 24h+ stale by the next run.
    _setup(monkeypatch)
    calls = {"n": 0}

    def fetch_once(query):
        calls["n"] += 1
        return _payload(["acme"])
    monkeypatch.setattr(D, "_brave_fetch", fetch_once)

    known: set[str] = set()
    D.discover_companies("controls engineer", tmp_path, True, known)
    assert calls["n"] == 5  # first call: one live fetch per ATS site

    # Age every written cache file to 25 hours old (past the old 24h TTL).
    cutoff = time.time() - 25 * 3600
    import os
    for f in tmp_path.glob("brave_*.json"):
        os.utime(f, (cutoff, cutoff))

    D.reset_run_memo()  # simulate a fresh process/run (new daily_run invocation)
    known2: set[str] = set()
    D.discover_companies("controls engineer", tmp_path, True, known2)
    assert calls["n"] == 5  # UNCHANGED -- the 25h-old cache is still fresh under the new TTL


def test_in_run_memo_dedupes_identical_query_within_one_run(tmp_path, monkeypatch):
    # The SAME keyword queried twice in one process (e.g. a literal duplicate
    # after --add-keyword, or two callers in the same run) must not re-fetch.
    _setup(monkeypatch)
    calls = {"n": 0}

    def fetch_once(query):
        calls["n"] += 1
        return _payload(["acme"])
    monkeypatch.setattr(D, "_brave_fetch", fetch_once)

    D.discover_companies("controls engineer", tmp_path, cache_enabled=False, known_slugs=set())
    assert calls["n"] == 5
    # cache_enabled=False (no disk cache at all) -- the IN-RUN memo is what
    # saves the second call, not the on-disk cache.
    D.discover_companies("controls engineer", tmp_path, cache_enabled=False, known_slugs=set())
    assert calls["n"] == 5  # unchanged: memoized in-process


def test_in_run_memo_is_per_keyword_not_global(tmp_path, monkeypatch):
    # A DIFFERENT keyword must still fetch live -- the memo is keyed by
    # (ats_site, keyword), not just "has discovery run this process".
    _setup(monkeypatch)
    calls = {"n": 0}

    def fetch_once(query):
        calls["n"] += 1
        return _payload(["acme"])
    monkeypatch.setattr(D, "_brave_fetch", fetch_once)

    D.discover_companies("controls engineer", tmp_path, cache_enabled=False, known_slugs=set())
    assert calls["n"] == 5
    D.discover_companies("mechanical engineer", tmp_path, cache_enabled=False, known_slugs=set())
    assert calls["n"] == 10  # a genuinely different keyword still fetches


def test_reset_run_memo_clears_between_runs(tmp_path, monkeypatch):
    _setup(monkeypatch)
    calls = {"n": 0}

    def fetch_once(query):
        calls["n"] += 1
        return _payload(["acme"])
    monkeypatch.setattr(D, "_brave_fetch", fetch_once)

    D.discover_companies("controls engineer", tmp_path, cache_enabled=False, known_slugs=set())
    assert calls["n"] == 5
    D.reset_run_memo()  # simulate a new daily_run process
    D.discover_companies("controls engineer", tmp_path, cache_enabled=False, known_slugs=set())
    assert calls["n"] == 10  # a NEW run re-fetches (memo doesn't leak across runs)


def test_cache_miss_behavior_unchanged_still_writes_cache(tmp_path, monkeypatch):
    # Cache-miss path must still write the fetched payload to disk exactly as
    # before -- only the READ side got a longer TTL + an in-run memo.
    _setup(monkeypatch)
    monkeypatch.setattr(D, "_brave_fetch", lambda q: _payload(["acme"]))
    D.discover_companies("controls engineer", tmp_path, cache_enabled=True, known_slugs=set())
    files = list(tmp_path.glob("brave_*.json"))
    assert len(files) == 5  # one per ATS site, exactly as before
