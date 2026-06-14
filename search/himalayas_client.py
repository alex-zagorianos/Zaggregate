"""Himalayas public API — free, no key, remote-only postings. Paginated;
the first HIMALAYAS_MAX_JOBS are fetched once per cache cycle as a single
feed and filtered client-side per keyword.

Quirks handled here: pubDate is a UNIX timestamp (int) and must become an
ISO string for search_engine._parse_created; minSalary/maxSalary come with
a salaryPeriod ("yearly"/"monthly"/"hourly") that needs annualizing."""
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import (
    HIMALAYAS_MAX_JOBS,
    HIMALAYAS_PAGE_SIZE,
    HIMALAYAS_RATE_LIMIT,
    HIMALAYAS_URL,
)
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, make_session

_TAG_RE = re.compile(r"<[^>]+>")

# salaryPeriod -> multiplier to annualize
_PERIOD_FACTOR = {
    "yearly": 1,
    "annual": 1,      # value actually returned by the API
    "annually": 1,
    "monthly": 12,
    "weekly": 52,
    "daily": 260,
    "hourly": 2080,
}


def _annualize(value, period: str) -> Optional[int]:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    amount *= _PERIOD_FACTOR.get((period or "yearly").lower(), 1)
    # Same sanity bounds as match.scorer's salary recovery.
    if 30_000 <= amount <= 500_000:
        return int(amount)
    return None


def _iso_from_unix(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


class HimalayasClient(JobAPIClient):
    def __init__(self, cache_dir: Optional[Path] = None, cache_enabled: bool = True):
        self.cache = FileCache("himalayas", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.session.headers["User-Agent"] = "JobSearchTool/1.0 (personal use)"
        self.limiter = RateLimiter(HIMALAYAS_RATE_LIMIT, quiet=True)

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        if page > 1:
            return {"jobs": []}  # whole feed handled on page 1

        if self.cache_enabled:
            cached = self.cache.get("feed")
            if cached is not None:
                return cached

        jobs: list[dict] = []
        offset = 0
        # The API ignores `limit` and always returns <=20, so advance the
        # offset by however many actually came back rather than a fixed step;
        # stop on an empty page or once we've collected MAX_JOBS.
        while len(jobs) < HIMALAYAS_MAX_JOBS:
            self.limiter.acquire()
            response = self.session.get(
                HIMALAYAS_URL,
                params={"limit": HIMALAYAS_PAGE_SIZE, "offset": offset},
                timeout=30,
            )
            response.raise_for_status()
            batch = response.json().get("jobs", [])
            if not batch:
                break
            jobs.extend(batch)
            offset += len(batch)

        data = {"jobs": jobs}
        if self.cache_enabled:
            self.cache.put("feed", data)
        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("jobs", []):
            title = item.get("title", "") or ""
            blob = f"{title} {' '.join(item.get('categories') or [])}"
            if not keyword_matches(source_keyword, blob):
                continue
            desc = _TAG_RE.sub(" ", item.get("description", "") or "")
            period = item.get("salaryPeriod", "")
            locations = item.get("locationRestrictions") or []
            results.append(JobResult(
                title=title,
                company=item.get("companyName", "Unknown"),
                location=", ".join(locations) if locations else "Remote",
                salary_min=_annualize(item.get("minSalary"), period),
                salary_max=_annualize(item.get("maxSalary"), period),
                description=desc[:3000],
                url=item.get("applicationLink") or item.get("guid", ""),
                source_keyword=source_keyword,
                created=_iso_from_unix(item.get("pubDate")),
                job_id=f"himalayas_{item.get('guid', '')}",
                source_api="himalayas",
            ))
        return results
