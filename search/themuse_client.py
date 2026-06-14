"""The Muse public jobs API — free, no key. The API has no keyword parameter,
so one HTTP fetch per (location, page) is cached and shared across keywords;
keyword filtering happens client-side in parse_results."""
import re
from pathlib import Path
from typing import Optional

from config import THEMUSE_BASE_URL, THEMUSE_CATEGORIES, THEMUSE_RATE_LIMIT
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, cache_key, make_session

_TAG_RE = re.compile(r"<[^>]+>")
_STOPWORDS = {"engineer", "engineering", "senior", "junior", "and", "or", "of", "the"}


def _strip_html(text: str) -> str:
    return _TAG_RE.sub(" ", text or "").replace("&amp;", "&").replace("&nbsp;", " ")


class TheMuseClient(JobAPIClient):
    def __init__(self, cache_dir: Optional[Path] = None, cache_enabled: bool = True):
        self.cache = FileCache("themuse", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.limiter = RateLimiter(THEMUSE_RATE_LIMIT, quiet=True)

    def search(
        self,
        keyword: str,
        location: str = "Cincinnati",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        # Keyword deliberately NOT in the cache key: the fetch is keyword-blind,
        # so 10 keywords share one cached page instead of 10 identical fetches.
        key = cache_key("themuse", location, page)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        self.limiter.acquire()
        params = [("page", page - 1)]  # The Muse pages are 0-based
        for cat in THEMUSE_CATEGORIES:
            params.append(("category", cat))
        response = self.session.get(THEMUSE_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if self.cache_enabled:
            self.cache.put(key, data)
        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        toks = [t for t in re.split(r"\W+", source_keyword.lower())
                if len(t) > 2 and t not in _STOPWORDS]
        results = []
        for item in raw.get("results", []):
            title = item.get("name", "Unknown")
            contents = _strip_html(item.get("contents", ""))
            tl, cl = title.lower(), contents.lower()
            # Keep if any significant keyword token is in the title, or all
            # tokens appear in the description.
            if toks and not (any(t in tl for t in toks)
                             or all(t in cl for t in toks)):
                continue
            locations = ", ".join(
                loc.get("name", "") for loc in item.get("locations", []))
            results.append(
                JobResult(
                    title=title,
                    company=(item.get("company") or {}).get("name", "Unknown"),
                    location=locations or "Unknown",
                    salary_min=None,  # The Muse does not publish salaries
                    salary_max=None,
                    description=contents[:3000],
                    url=(item.get("refs") or {}).get("landing_page", ""),
                    source_keyword=source_keyword,
                    created=item.get("publication_date", ""),
                    job_id=str(item.get("id", "")),
                    source_api="themuse",
                )
            )
        return results
