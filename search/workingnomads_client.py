"""WorkingNomads public JSON feed — free, no key, remote-only postings. Single
feed (no pagination, no server-side keyword search): fetched once per cache
cycle and filtered client-side per keyword (like remoteok/remotive/arbeitnow)."""
from typing import Optional

from models import JobResult
from search.single_feed_client import SingleFeedClient

WORKINGNOMADS_URL = "https://www.workingnomads.com/api/exposed_jobs/"
WORKINGNOMADS_RATE_LIMIT = 5


class WorkingNomadsClient(SingleFeedClient):
    cache_subdir = "workingnomads"
    rate_limit = WORKINGNOMADS_RATE_LIMIT

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
            response = self.session.get(WORKINGNOMADS_URL, timeout=30)
            response.raise_for_status()
            payload = response.json()
            # Defensive: API always documents a JSON array, but never trust an
            # unauthenticated feed's shape blindly (dict/None -> no jobs, not a crash).
            jobs = payload if isinstance(payload, list) else []
            return {"jobs": [j for j in jobs if isinstance(j, dict)]}

        return self._cached("feed", fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("jobs", []) or []:
            title = item.get("title", "") or ""
            category = item.get("category_name", "") or ""
            tags = item.get("tags")
            tags_blob = " ".join(tags) if isinstance(tags, list) else (tags or "")
            blob = f"{title} {category} {tags_blob}"
            if not keyword_matches(source_keyword, blob):
                continue
            desc = self.strip_html(item.get("description", "") or "")
            results.append(JobResult(
                title=title,
                company=item.get("company_name", "Unknown") or "Unknown",
                location=item.get("location") or "Remote",
                salary_min=None,
                salary_max=None,
                description=desc[:3000],
                url=item.get("url", "") or "",
                source_keyword=source_keyword,
                created=item.get("pub_date", "") or "",
                job_id=f"workingnomads_{item.get('url', '')}",
                source_api="workingnomads",
            ))
        return results
