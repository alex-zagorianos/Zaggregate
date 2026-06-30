"""Arbeitnow public job-board API — free, no key. Single-document feed fetched
once per cache cycle and filtered client-side per keyword (like Remotive)."""
from datetime import datetime, timezone
from typing import Optional

from config import ARBEITNOW_RATE_LIMIT, ARBEITNOW_URL
from models import JobResult
from search.single_feed_client import SingleFeedClient


class ArbeitnowClient(SingleFeedClient):
    cache_subdir = "arbeitnow"
    rate_limit = ARBEITNOW_RATE_LIMIT

    def search(self, keyword: str, location: str = "", salary_min: Optional[int] = None,
               page: int = 1) -> dict:
        if page > 1:
            return {"data": []}

        def fetch():
            self.limiter.acquire()
            resp = self.session.get(ARBEITNOW_URL, timeout=30)
            resp.raise_for_status()
            return {"data": resp.json().get("data", [])}

        return self._cached("feed", fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("data", []):
            title = item.get("title", "") or ""
            blob = f"{title} {' '.join(item.get('tags') or [])}"
            if not keyword_matches(source_keyword, blob):
                continue
            created = item.get("created_at")
            created_iso = ""
            if isinstance(created, (int, float)):
                created_iso = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            results.append(JobResult(
                title=title,
                company=item.get("company_name", "Unknown") or "Unknown",
                location=item.get("location") or ("Remote" if item.get("remote") else ""),
                salary_min=None,
                salary_max=None,
                description=self.strip_html(item.get("description", "") or "")[:3000],
                url=item.get("url", "") or "",
                source_keyword=source_keyword,
                created=created_iso,
                job_id=f"arbeitnow_{item.get('slug', '')}",
                source_api="arbeitnow",
            ))
        return results
