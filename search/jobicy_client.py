"""Jobicy public API — free, no key, remote-only postings. Single feed
(max 50 jobs) fetched once per cache cycle and filtered client-side per keyword.
The industry slice is derived from the active project's field (was hardcoded to
'engineering', which returned 0 for any non-eng seeker). No salary fields."""
from typing import Optional

from config import JOBICY_COUNT, JOBICY_RATE_LIMIT, JOBICY_URL
from models import JobResult
from search.single_feed_client import SingleFeedClient


class JobicyClient(SingleFeedClient):
    cache_subdir = "jobicy"
    rate_limit = JOBICY_RATE_LIMIT

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        if page > 1:
            return {"jobs": []}  # single-document feed; no further pages

        from search.source_taxonomy import jobicy_industry
        industry = jobicy_industry()  # None → omit the param (all remote jobs)

        def fetch():
            self.limiter.acquire()
            params = {"count": JOBICY_COUNT}
            if industry:
                params["industry"] = industry
            response = self.session.get(JOBICY_URL, params=params, timeout=30)
            response.raise_for_status()
            return {"jobs": response.json().get("jobs", [])}

        # Industry in the cache key so an eng and a health project don't collide.
        return self._cached(f"feed:{industry or 'all'}", fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("jobs", []):
            title = item.get("jobTitle", "") or ""
            blob = f"{title} {' '.join(item.get('jobIndustry') or [])}"
            if not keyword_matches(source_keyword, blob):
                continue
            desc = self.strip_html(item.get("jobDescription", "") or "")
            results.append(JobResult(
                title=title,
                company=item.get("companyName", "Unknown"),
                location=item.get("jobGeo") or "Remote",
                salary_min=None,
                salary_max=None,
                description=desc[:3000],
                url=item.get("url", ""),
                source_keyword=source_keyword,
                created=item.get("pubDate", ""),
                job_id=f"jobicy_{item.get('id', '')}",
                source_api="jobicy",
            ))
        return results
