"""RemoteOK public JSON feed — free, no key, remote-only postings. The feed is
one document (no pagination, no server-side keyword search): a single cached
fetch is filtered client-side per keyword."""
import re
from pathlib import Path
from typing import Optional

from config import REMOTEOK_RATE_LIMIT, REMOTEOK_URL
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, make_session, to_float

_TAG_RE = re.compile(r"<[^>]+>")
_STOPWORDS = {"engineer", "engineering", "senior", "junior", "and", "or", "of", "the"}


class RemoteOKClient(JobAPIClient):
    def __init__(self, cache_dir: Optional[Path] = None, cache_enabled: bool = True):
        self.cache = FileCache("remoteok", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.session.headers["User-Agent"] = "JobSearchTool/1.0 (personal use)"
        self.limiter = RateLimiter(REMOTEOK_RATE_LIMIT, quiet=True)

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
        response = self.session.get(REMOTEOK_URL, timeout=30)
        response.raise_for_status()
        items = response.json()
        # First element is a legal/attribution notice, not a job.
        jobs = [i for i in items if isinstance(i, dict) and i.get("position")]
        data = {"jobs": jobs}

        if self.cache_enabled:
            self.cache.put("feed", data)
        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        toks = [t for t in re.split(r"\W+", source_keyword.lower())
                if len(t) > 2 and t not in _STOPWORDS]
        # Keywords that reduce to nothing distinctive (e.g. "R&D engineer" ->
        # [] once "engineer" is stripped) carry no remote-board signal; match
        # nothing rather than dumping the whole feed.
        if not toks:
            return []
        results = []
        for item in raw.get("jobs", []):
            title = item.get("position", "Unknown")
            desc = _TAG_RE.sub(" ", item.get("description", ""))
            tags = " ".join(item.get("tags", []) or [])
            # Match on title + tags only. The description is long enough that a
            # single passing mention of "automation"/"design" would qualify
            # unrelated jobs, so it is deliberately excluded from the surface.
            blob = f"{title} {tags}".lower()
            if not any(t in blob for t in toks):
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
