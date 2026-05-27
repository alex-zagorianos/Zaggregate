import json
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from config import (
    ADZUNA_APP_ID,
    ADZUNA_APP_KEY,
    ADZUNA_BASE_URL,
    ADZUNA_RATE_LIMIT,
    ADZUNA_RESULTS_PER_PAGE,
    CACHE_DIR,
    CACHE_TTL_HOURS,
)
from models import JobResult
from search.base_client import JobAPIClient


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
        self.cache_dir = (cache_dir or CACHE_DIR) / "adzuna"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_enabled = cache_enabled
        self._call_timestamps: deque[float] = deque(maxlen=ADZUNA_RATE_LIMIT)

    def search(
        self,
        keyword: str,
        location: str = "Cincinnati",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        if self.cache_enabled:
            cache_key = self._cache_key(keyword, location, page)
            cached = self._read_cache(cache_key)
            if cached is not None:
                return cached

        self._rate_limit()

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

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        self._call_timestamps.append(time.time())

        if self.cache_enabled:
            self._write_cache(cache_key, data)

        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        for item in raw.get("results", []):
            results.append(
                JobResult(
                    title=item.get("title", "Unknown"),
                    company=item.get("company", {}).get("display_name", "Unknown"),
                    location=item.get("location", {}).get("display_name", "Unknown"),
                    salary_min=item.get("salary_min"),
                    salary_max=item.get("salary_max"),
                    description=item.get("description", ""),
                    url=item.get("redirect_url", ""),
                    source_keyword=source_keyword,
                    created=item.get("created", ""),
                    job_id=str(item.get("id", "")),
                    source_api="adzuna",
                )
            )
        return results

    def _rate_limit(self):
        if len(self._call_timestamps) >= ADZUNA_RATE_LIMIT:
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
