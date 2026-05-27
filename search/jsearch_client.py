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
    JSEARCH_BASE_URL,
    JSEARCH_RAPIDAPI_HOST,
    JSEARCH_RAPIDAPI_KEY,
    JSEARCH_RATE_LIMIT,
    JSEARCH_RESULTS_PER_PAGE,
)
from models import JobResult
from search.base_client import JobAPIClient


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
        self.cache_dir = (cache_dir or CACHE_DIR) / "jsearch"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_enabled = cache_enabled
        self._call_timestamps: deque[float] = deque(maxlen=JSEARCH_RATE_LIMIT)

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
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": JSEARCH_RAPIDAPI_HOST,
        }
        params = {
            "query": f"{keyword} in {location}",
            "page": str(page),
            "num_pages": "1",
            "results_wanted": JSEARCH_RESULTS_PER_PAGE,
        }

        response = requests.get(JSEARCH_BASE_URL, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        self._call_timestamps.append(time.time())

        if self.cache_enabled:
            self._write_cache(cache_key, data)

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
                    salary_min=item.get("job_min_salary"),
                    salary_max=item.get("job_max_salary"),
                    description=item.get("job_description", ""),
                    url=item.get("job_apply_link") or item.get("job_google_link", ""),
                    source_keyword=source_keyword,
                    created=item.get("job_posted_at_datetime_utc") or "",
                    job_id=f"jsearch_{item.get('job_id', '')}",
                    source_api="jsearch",
                )
            )
        return results

    def _rate_limit(self):
        if len(self._call_timestamps) >= JSEARCH_RATE_LIMIT:
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
