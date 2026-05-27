import json
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from config import (
    CACHE_DIR,
    CACHE_TTL_HOURS,
    USAJOBS_API_KEY,
    USAJOBS_BASE_URL,
    USAJOBS_RATE_LIMIT,
    USAJOBS_RESULTS_PER_PAGE,
    USAJOBS_USER_AGENT,
)
from models import JobResult
from search.base_client import JobAPIClient


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
        self.cache_dir = (cache_dir or CACHE_DIR) / "usajobs"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_enabled = cache_enabled
        self._call_timestamps: deque[float] = deque(maxlen=USAJOBS_RATE_LIMIT)

    def search(
        self,
        keyword: str,
        location: str = "Cincinnati, OH",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        if self.cache_enabled:
            cache_key = self._cache_key(keyword, location, page)
            cached = self._read_cache(cache_key)
            if cached is not None:
                return cached

        self._rate_limit()

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

        response = requests.get(USAJOBS_BASE_URL, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        self._call_timestamps.append(time.time())

        if self.cache_enabled:
            self._write_cache(cache_key, data)

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
                try:
                    salary_min = float(remuneration[0].get("MinimumRange", 0)) or None
                    salary_max = float(remuneration[0].get("MaximumRange", 0)) or None
                except (ValueError, TypeError):
                    pass

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
        location = location.strip()
        # Ensure "City, ST" format — USAJobs needs state abbreviation
        if "," not in location:
            return location + ", OH"
        return location

    def _rate_limit(self):
        if len(self._call_timestamps) >= USAJOBS_RATE_LIMIT:
            oldest = self._call_timestamps[0]
            elapsed = time.time() - oldest
            if elapsed < 60:
                sleep_time = 60 - elapsed
                print(f"  Rate limit: sleeping {sleep_time:.1f}s...")
                time.sleep(sleep_time)

    def _cache_key(self, keyword: str, location: str, page: int) -> str:
        slug = keyword.lower().replace(" ", "_").replace("/", "_")
        loc_slug = location.lower().replace(" ", "_").replace(",", "")
        return f"{slug}_{loc_slug}_page{page}"

    def _read_cache(self, cache_key: str) -> Optional[dict]:
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None
        modified = datetime.fromtimestamp(cache_file.stat().st_mtime)
        if datetime.now() - modified > timedelta(hours=CACHE_TTL_HOURS):
            return None
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_cache(self, cache_key: str, data: dict):
        cache_file = self.cache_dir / f"{cache_key}.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
