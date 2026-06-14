from pathlib import Path
from typing import Optional

from config import (
    CACHE_DIR,
    JSEARCH_BASE_URL,
    JSEARCH_MONTHLY_LIMIT,
    JSEARCH_RAPIDAPI_HOST,
    JSEARCH_RAPIDAPI_KEY,
    JSEARCH_RATE_LIMIT,
)
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import (
    FileCache,
    MonthlyQuota,
    RateLimiter,
    cache_key,
    make_session,
    to_float,
)


class JSearchClient(JobAPIClient):
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = True,
    ):
        self.api_key = api_key or JSEARCH_RAPIDAPI_KEY
        if not self.api_key:
            raise ValueError(
                "JSearch API key missing. Set JSEARCH_RAPIDAPI_KEY in .env"
            )
        self.cache = FileCache("jsearch", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.limiter = RateLimiter(JSEARCH_RATE_LIMIT)
        self.quota = MonthlyQuota(
            (cache_dir or CACHE_DIR) / "jsearch_usage.json", JSEARCH_MONTHLY_LIMIT
        )
        self._quota_warned = False

    def search(
        self,
        keyword: str,
        location: str = "Cincinnati, OH",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        key = cache_key("jsearch", keyword, location, salary_min, page)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        # Protect the 200/month free-tier cap. Cached hits above don't count.
        if not self.quota.try_increment():
            if not self._quota_warned:
                print(
                    "  [jsearch] Monthly free-tier cap "
                    f"({JSEARCH_MONTHLY_LIMIT}) reached — skipping JSearch this month."
                )
                self._quota_warned = True
            return {"data": []}

        self.limiter.acquire()

        headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": JSEARCH_RAPIDAPI_HOST,
        }
        params = {
            "query": f"{keyword} in {location}",
            "page": str(page),
            "num_pages": "1",
        }

        response = self.session.get(
            JSEARCH_BASE_URL, headers=headers, params=params, timeout=30
        )
        response.raise_for_status()
        data = response.json()

        if self.cache_enabled:
            self.cache.put(key, data)

        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        for item in raw.get("data", []):
            city = item.get("job_city") or ""
            state = item.get("job_state") or ""
            location_parts = [p for p in [city, state] if p]
            location = ", ".join(location_parts) if location_parts else item.get("job_country", "")

            results.append(
                JobResult(
                    title=item.get("job_title", "Unknown"),
                    company=item.get("employer_name", "Unknown"),
                    location=location,
                    salary_min=to_float(item.get("job_min_salary")),
                    salary_max=to_float(item.get("job_max_salary")),
                    description=item.get("job_description", ""),
                    url=item.get("job_apply_link") or item.get("job_google_link", ""),
                    source_keyword=source_keyword,
                    created=item.get("job_posted_at_datetime_utc") or "",
                    job_id=f"jsearch_{item.get('job_id', '')}",
                    source_api="jsearch",
                )
            )
        return results
