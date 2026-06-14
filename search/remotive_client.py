"""Remotive public API — free, no key, remote-only postings. Their legal
notice asks for <=4 fetches/day, so the whole feed is fetched once and
filtered client-side per keyword (the 24h cache keeps us at ~1 fetch/day)."""
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import REMOTIVE_RATE_LIMIT, REMOTIVE_URL
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, make_session

_TAG_RE = re.compile(r"<[^>]+>")


class RemotiveClient(JobAPIClient):
    def __init__(self, cache_dir: Optional[Path] = None, cache_enabled: bool = True):
        self.cache = FileCache("remotive", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.session.headers["User-Agent"] = "JobSearchTool/1.0 (personal use)"
        self.limiter = RateLimiter(REMOTIVE_RATE_LIMIT, quiet=True)

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        if page > 1:
            return {"jobs": []}  # single-document feed; no further pages

        if self.cache_enabled:
            cached = self.cache.get("feed")
            if cached is not None:
                return cached

        self.limiter.acquire()
        response = self.session.get(REMOTIVE_URL, timeout=30)
        response.raise_for_status()
        data = {"jobs": response.json().get("jobs", [])}

        if self.cache_enabled:
            self.cache.put("feed", data)
        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("jobs", []):
            title = item.get("title", "") or ""
            blob = f"{title} {item.get('category', '')} {' '.join(item.get('tags') or [])}"
            if not keyword_matches(source_keyword, blob):
                continue
            desc = _TAG_RE.sub(" ", item.get("description", "") or "")
            # Remotive salary is freeform text ("$130,000 - $160,000"); prepend
            # it so match.scorer's salary_from_text can recover the range.
            salary_text = (item.get("salary") or "").strip()
            if salary_text:
                desc = f"Salary: {salary_text}\n{desc}"
            results.append(JobResult(
                title=title,
                company=item.get("company_name", "Unknown"),
                location=item.get("candidate_required_location") or "Remote",
                salary_min=None,
                salary_max=None,
                description=desc[:3000],
                url=item.get("url", ""),
                source_keyword=source_keyword,
                created=item.get("publication_date", ""),
                job_id=f"remotive_{item.get('id', '')}",
                source_api="remotive",
            ))
        return results
