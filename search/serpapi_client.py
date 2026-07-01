"""SerpApi Google-Jobs backend — BYO-paid, key-gated, quota-conserving
(mirrors jsearch_client.py). Key from SERPAPI_KEY env or secrets/serpapi_key.
Covers Indeed/LinkedIn/Glassdoor/ZipRecruiter via Google Jobs aggregation."""
from pathlib import Path
from typing import Optional

import config
from config import (
    CACHE_DIR,
    SERPAPI_KEY,
    SERPAPI_MONTHLY_LIMIT,
    SERPAPI_RATE_LIMIT,
    SERPAPI_URL,
)
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, MonthlyQuota, RateLimiter, cache_key, make_session


def _resolve_key(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    if SERPAPI_KEY:
        return SERPAPI_KEY
    try:
        return (config.SECRETS_DIR / "serpapi_key").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


class SerpApiClient(JobAPIClient):
    # Keyword-parameterized + stateless across keywords → SearchEngine may fetch
    # each keyword concurrently (see search_engine.run_full_search).
    parallel_keywords = True

    def __init__(self, api_key: Optional[str] = None, cache_dir: Optional[Path] = None,
                 cache_enabled: bool = True):
        self.api_key = _resolve_key(api_key)
        if not self.api_key:
            raise ValueError(
                "SerpApi key missing. Set SERPAPI_KEY in .env or put it in secrets/serpapi_key")
        self.cache = FileCache("serpapi", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.limiter = RateLimiter(SERPAPI_RATE_LIMIT)
        self.quota = MonthlyQuota((cache_dir or CACHE_DIR) / "serpapi_usage.json", SERPAPI_MONTHLY_LIMIT)
        self._quota_warned = False

    def search(self, keyword: str, location: str = "Cincinnati, OH",
               salary_min: Optional[int] = None, page: int = 1) -> dict:
        # SerpApi Google Jobs is single-page here; a page>1 request would re-fetch
        # page 1, spend another quota unit, and return duplicates. Short-circuit.
        if page > 1:
            return {"jobs_results": []}
        engine = config.SERPAPI_ENGINE or "google_jobs"
        # Engine is part of the cache identity: the same query on google_jobs vs
        # indeed returns different results, so they must not share a cache slot.
        key = cache_key("serpapi", engine, keyword, location, page)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        if not self.quota.try_increment():
            if not self._quota_warned:
                print(f"  [serpapi] Monthly cap ({SERPAPI_MONTHLY_LIMIT}) reached — skipping this month.")
                self._quota_warned = True
            return {"jobs_results": []}
        self.limiter.acquire()
        if engine == "indeed":
            # SerpApi's Indeed engine takes a separate location param (`l`).
            params = {"engine": "indeed", "q": keyword, "l": location,
                      "api_key": self.api_key}
        else:
            params = {"engine": engine, "q": f"{keyword} {location}".strip(),
                      "api_key": self.api_key}
        try:
            resp = self.session.get(SERPAPI_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            self.quota.decrement()
            raise
        if self.cache_enabled:
            self.cache.put(key, data)
        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        # google_jobs -> "jobs_results"; indeed engine -> "jobs_results" too but a
        # different item shape. Read both defensively; an unrecognized shape (no
        # recognizable job list) yields [] rather than raising.
        items = raw.get("jobs_results")
        if not isinstance(items, list):
            return []
        results = []
        for item in items:
            if not isinstance(item, dict):
                continue
            opts = item.get("apply_options") or []
            url = ((opts[0].get("link") if opts else "")
                   or item.get("link", "")           # indeed engine: direct link
                   or item.get("share_link", "") or "")
            posted = ((item.get("detected_extensions") or {}).get("posted_at", "")
                      or item.get("date", "") or "")
            job_id = item.get("job_id") or item.get("job_key") or ""
            results.append(JobResult(
                title=item.get("title", "") or "",
                company=(item.get("company_name") or item.get("company") or "Unknown"),
                location=item.get("location", "") or "",
                salary_min=None,
                salary_max=None,
                description=(item.get("description", "") or item.get("snippet", "") or "")[:3000],
                url=url,
                source_keyword=source_keyword,
                created=posted,
                job_id=f"serpapi_{job_id}",
                source_api="serpapi",
            ))
        return results
