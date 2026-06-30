"""Jobicy public API — free, no key, remote-only postings. Single feed
(max 50 jobs, engineering category) fetched once per cache cycle and
filtered client-side per keyword. No salary fields in the API."""
from typing import Optional

from config import JOBICY_COUNT, JOBICY_INDUSTRY, JOBICY_RATE_LIMIT, JOBICY_URL
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

        def fetch():
            self.limiter.acquire()
            response = self.session.get(
                JOBICY_URL,
                params={"count": JOBICY_COUNT, "industry": JOBICY_INDUSTRY},
                timeout=30,
            )
            response.raise_for_status()
            return {"jobs": response.json().get("jobs", [])}

        return self._cached("feed", fetch)

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
