"""RemoteOK public JSON feed — free, no key, remote-only postings. The feed is
one document (no pagination, no server-side keyword search): a single cached
fetch is filtered client-side per keyword."""
from typing import Optional

from config import REMOTEOK_RATE_LIMIT, REMOTEOK_URL
from models import JobResult
from search.http_util import to_float
from search.single_feed_client import SingleFeedClient


class RemoteOKClient(SingleFeedClient):
    cache_subdir = "remoteok"
    rate_limit = REMOTEOK_RATE_LIMIT

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
            response = self.session.get(REMOTEOK_URL, timeout=30)
            response.raise_for_status()
            items = response.json()
            # First element is a legal/attribution notice, not a job.
            jobs = [i for i in items if isinstance(i, dict) and i.get("position")]
            return {"jobs": jobs}

        return self._cached("feed", fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("jobs", []):
            title = item.get("position", "Unknown")
            desc = self.strip_html(item.get("description", ""))
            tags = " ".join(item.get("tags", []) or [])
            # Match on title + tags only (the description is long enough that a
            # single passing mention of "automation"/"design" would qualify
            # unrelated jobs). Route through the boolean query engine like the
            # other feeds so "phrase", OR, and NOT/- operators are honored — the
            # old stopword token matcher silently ignored them.
            if not keyword_matches(source_keyword, f"{title} {tags}"):
                continue
            results.append(
                JobResult(
                    title=title,
                    company=item.get("company", "Unknown"),
                    location=item.get("location") or "Remote",
                    salary_min=to_float(item.get("salary_min")) or None,
                    salary_max=to_float(item.get("salary_max")) or None,
                    description=desc[:3000],
                    url=item.get("url", ""),
                    source_keyword=source_keyword,
                    created=item.get("date", ""),
                    job_id=str(item.get("id", "")),
                    source_api="remoteok",
                )
            )
        return results
