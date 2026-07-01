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
        key = cache_key("adzuna", self.country, keyword, location, salary_min, page)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        self.limiter.acquire()

        url = f"{self.base_url}/{page}"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": keyword,
            "where": location,
            "results_per_page": ADZUNA_RESULTS_PER_PAGE,
            "content-type": "application/json",
        }
        if salary_min is not None:
            params["salary_min"] = salary_min

        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if self.cache_enabled:
            self.cache.put(key, data)

        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        for item in raw.get("results", []):
            results.append(
                JobResult(
                    title=item.get("title", "Unknown"),
                    company=(item.get("company") or {}).get("display_name", "Unknown"),
                    location=(item.get("location") or {}).get("display_name", "Unknown"),
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
