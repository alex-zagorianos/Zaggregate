from pathlib import Path
from typing import Optional

from config import (
    USAJOBS_API_KEY,
    USAJOBS_BASE_URL,
    USAJOBS_RATE_LIMIT,
    USAJOBS_RESULTS_PER_PAGE,
    USAJOBS_USER_AGENT,
)
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, cache_key, make_session, to_float


class USAJobsClient(JobAPIClient):
    def __init__(
        self,
        api_key: Optional[str] = None,
        user_agent: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = True,
    ):
        self.api_key = api_key or USAJOBS_API_KEY
        self.user_agent = user_agent or USAJOBS_USER_AGENT
        if not self.api_key or not self.user_agent:
            raise ValueError(
                "USAJobs credentials missing. Set USAJOBS_API_KEY and USAJOBS_USER_AGENT in .env. "
                "Register at https://developer.usajobs.gov/"
            )
        self.cache = FileCache("usajobs", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.limiter = RateLimiter(USAJOBS_RATE_LIMIT)

    def search(
        self,
        keyword: str,
        location: str = "Cincinnati, OH",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        key = cache_key("usajobs", keyword, location, salary_min, page)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        self.limiter.acquire()

        headers = {
            "Authorization-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Host": "data.usajobs.gov",
        }
        params = {
            "Keyword": keyword,
            "LocationName": self._normalize_location(location),
            "ResultsPerPage": USAJOBS_RESULTS_PER_PAGE,
            "Page": page,
        }
        if salary_min is not None:
            params["RemunerationMinimumAmount"] = salary_min

        response = self.session.get(
            USAJOBS_BASE_URL, headers=headers, params=params, timeout=30
        )
        response.raise_for_status()
        data = response.json()

        if self.cache_enabled:
            self.cache.put(key, data)

        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        items = (
            raw.get("SearchResult", {})
            .get("SearchResultItems", [])
        )
        for item in items:
            desc = item.get("MatchedObjectDescriptor", {})

            locations = desc.get("PositionLocation", [])
            location = locations[0].get("LocationName", "") if locations else ""

            remuneration = desc.get("PositionRemuneration", [])
            salary_min = salary_max = None
            if remuneration:
                salary_min = to_float(remuneration[0].get("MinimumRange"))
                salary_max = to_float(remuneration[0].get("MaximumRange"))

            results.append(
                JobResult(
                    title=desc.get("PositionTitle", "Unknown"),
                    company=desc.get("OrganizationName", "Unknown"),
                    location=location,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    description=desc.get("QualificationSummary", ""),
                    url=desc.get("PositionURI", ""),
                    source_keyword=source_keyword,
                    created=desc.get("PublicationStartDate", ""),
                    job_id=f"usajobs_{desc.get('PositionID', '')}",
                    source_api="usajobs",
                )
            )
        return results

    def _normalize_location(self, location: str) -> str:
        # Return the caller's location verbatim (just trimmed). Previously this
        # appended ", OH" to any comma-less value, silently rewriting "Austin"
        # to "Austin, OH" and "Remote" to "Remote, OH".
        return location.strip()
