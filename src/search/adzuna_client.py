from pathlib import Path
from typing import Optional

import config
from config import (
    ADZUNA_RATE_LIMIT,
    ADZUNA_RESULTS_PER_PAGE,
)
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, cache_key, make_session, to_float
from search.remote_intent import is_remote_only

# Cache-schema version for the remote-intent tagging path. Bump this whenever
# is_remote_only()/the remote-fan-copy detection semantics change so an OLDER
# cache entry (written under a different remote-tagging meaning) can never be
# silently read back and misinterpreted under new logic — it's folded into the
# cache key, so a version bump is a one-time, scoped invalidation of only the
# affected entries (they simply miss and re-fetch) rather than a manual
# cache-wide TTL/clear firefight.
_CACHE_SCHEMA_VERSION = 1


class AdzunaClient(JobAPIClient):
    # Keyword-parameterized + stateless across keywords → SearchEngine may fetch
    # each keyword concurrently (see search_engine.run_full_search).
    parallel_keywords = True

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        country: Optional[str] = None,
    ):
        # Re-resolve env-then-secret at construction so a key pasted into the
        # in-app box after import is honored (config's module constant froze at
        # import). An explicit arg still wins for tests.
        self.app_id = app_id or config.resolve_secret("ADZUNA_APP_ID", "adzuna_app_id")
        self.app_key = app_key or config.resolve_secret("ADZUNA_APP_KEY", "adzuna_app_key")
        if not self.app_id or not self.app_key:
            raise ValueError(
                "Adzuna API credentials missing. Set ADZUNA_APP_ID and ADZUNA_APP_KEY in .env"
            )
        # One free key serves ~19 countries; only the /{cc}/ path segment changes.
        self.country = (country or config.ADZUNA_COUNTRY or "us").strip().lower() or "us"
        self.base_url = config.adzuna_country_url(self.country)
        self.cache = FileCache("adzuna", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.limiter = RateLimiter(ADZUNA_RATE_LIMIT)

    def search(
        self,
        keyword: str,
        location: str = "Cincinnati",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        # Remote-only intent: geocoding the literal string "Remote" into `where`
        # returns 0 (Adzuna resolves it to no place). Per the documented remote
        # strategy (research-sources §3/§G), instead put "remote" into `what`
        # (which Adzuna appends to remote postings' title/description) and blank
        # `where` so the search runs nationwide. Non-remote locations are
        # UNCHANGED — the branch below is skipped and `where` carries the metro.
        remote = is_remote_only(location)
        what = f"remote {keyword}".strip() if remote else keyword
        where = "" if remote else location
        # Strip a country-name tail that names THIS client's routed country: the
        # country already lives in the URL path, and Adzuna's geocoder returns 0
        # for a where-string carrying it (live-verified S35b on /gb/: 'London'
        # -> 231 results, 'London, United Kingdom' -> 0). A US "City, ST" tail
        # never matches a country name, so US behavior is byte-identical.
        if where:
            tail_cc = config.location_country_tail(where)
            if tail_cc and tail_cc == self.country:
                where = where.rsplit(",", 1)[0].strip()

        key = cache_key("adzuna", self.country, what, where, salary_min, page,
                        _CACHE_SCHEMA_VERSION)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                # The _remote_intent flag is stripped before caching (cache stays
                # API-shaped), so RE-DERIVE it on read from the same `remote`
                # boolean this search already computed. Without this, a cached
                # remote-only response loses its (Remote) row tags and those
                # fan-out metro rows score location=0 against a Remote search and
                # drop out of Top Picks on every search after the first (24h TTL).
                if remote:
                    cached = dict(cached)
                    cached["_remote_intent"] = True
                return cached

        self.limiter.acquire()

        url = f"{self.base_url}/{page}"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": what,
            "results_per_page": ADZUNA_RESULTS_PER_PAGE,
            "content-type": "application/json",
        }
        # Only send `where` when it's a real place — an empty `where` on the
        # remote path means "nationwide" (omitting it is the compliant way to
        # avoid the geocode-to-nothing that produced the 0-result bug).
        if where:
            params["where"] = where
        if salary_min is not None:
            params["salary_min"] = salary_min

        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        # Mark the payload so parse_results can tag rows as remote-acceptable
        # (survive the downstream location gate for a remote_ok user). This key
        # is stripped before caching so cache contents stay API-shaped.
        if remote:
            data = dict(data)
            data["_remote_intent"] = True

        if self.cache_enabled:
            to_cache = {k: v for k, v in data.items() if k != "_remote_intent"}
            self.cache.put(key, to_cache)

        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        remote_intent = bool(raw.get("_remote_intent"))
        raw_rows = raw.get("results", [])
        # A raw page shorter than the requested results_per_page means Adzuna
        # has no further page for this query — the engine reads this flag and
        # skips the follow-up request that would only burn a rate-limited slot.
        self._last_page_short = len(raw_rows) < ADZUNA_RESULTS_PER_PAGE
        results = []
        for item in raw_rows:
            loc = (item.get("location") or {}).get("display_name", "Unknown")
            # On the remote path, tag a row as remote ONLY when its own
            # title/description actually says "remote" — Adzuna fan-copies remote
            # jobs across the 10 largest metros with "remote" appended, so this is
            # a reliable per-row signal (research-sources §G) and avoids labeling a
            # non-remote row remote. Keeps the origin metro ("Austin, TX" ->
            # "Austin, TX (Remote)") so the downstream location gate keeps it for
            # a remote_ok user while the real city stays visible.
            if remote_intent and loc and "remote" not in loc.lower():
                blob = f"{item.get('title', '')} {item.get('description', '')}".lower()
                if "remote" in blob:
                    loc = f"{loc} (Remote)"
            results.append(
                JobResult(
                    title=item.get("title", "Unknown"),
                    company=(item.get("company") or {}).get("display_name", "Unknown"),
                    location=loc,
                    salary_min=to_float(item.get("salary_min")),
                    salary_max=to_float(item.get("salary_max")),
                    description=item.get("description", ""),
                    url=item.get("redirect_url", ""),
                    source_keyword=source_keyword,
                    created=item.get("created", ""),
                    job_id=str(item.get("id", "")),
                    source_api="adzuna",
                )
            )
        return results
