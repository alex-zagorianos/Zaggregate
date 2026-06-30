from pathlib import Path
from typing import Optional

from config import (
    ADZUNA_APP_ID,
    ADZUNA_APP_KEY,
    ADZUNA_BASE_URL,
    ADZUNA_RATE_LIMIT,
    ADZUNA_RESULTS_PER_PAGE,
)
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, cache_key, make_session, to_float


class AdzunaClient(JobAPIClient):
    def __init__(
        self,
        app_id: Optional[str] = None,
        app_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = True,
    ):
        self.app_id = app_id or ADZUNA_APP_ID
        self.app_key = app_key or ADZUNA_APP_KEY
        if not self.app_id or not self.app_key:
            raise ValueError(
                "Adzuna API credentials missing. Set ADZUNA_APP_ID and ADZUNA_APP_KEY in .env"
            )
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
        key = cache_key("adzuna", keyword, location, salary_min, page)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        self.limiter.acquire()

        url = f"{ADZUNA_BASE_URL}/{page}"
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
