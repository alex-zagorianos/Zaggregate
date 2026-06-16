"""The Muse public jobs API — free, no key. The API has no keyword parameter,
so one HTTP fetch per (location, page) is cached and shared across keywords;
keyword filtering happens client-side in parse_results."""
from typing import Optional

from config import THEMUSE_BASE_URL, THEMUSE_CATEGORIES, THEMUSE_RATE_LIMIT
from models import JobResult
from search.http_util import cache_key
from search.single_feed_client import SingleFeedClient


def _strip_html(text: str) -> str:
    # The Muse contents carry HTML entities the base stripper leaves alone; decode
    # the two that show up in practice on top of the shared tag removal.
    return (SingleFeedClient.strip_html(text)
            .replace("&amp;", "&").replace("&nbsp;", " "))


class TheMuseClient(SingleFeedClient):
    cache_subdir = "themuse"
    rate_limit = THEMUSE_RATE_LIMIT
    # The Muse needs no custom User-Agent; the previous client sent none at all,
    # but a polite default is harmless and matches the other feeds.

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

        def fetch():
            self.limiter.acquire()
            params = [("page", page - 1)]  # The Muse pages are 0-based
            for cat in THEMUSE_CATEGORIES:
                params.append(("category", cat))
            response = self.session.get(THEMUSE_BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            return response.json()

        return self._cached(key, fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("results", []):
            title = item.get("name", "Unknown")
            contents = _strip_html(item.get("contents", ""))
            # Route through the boolean query engine like the other feeds so
            # "phrase", OR, and NOT/- operators are honored (the old stopword
            # token matcher silently ignored them, letting `NOT senior` still
            # match "Senior ..."). Match on title + contents.
            if not keyword_matches(source_keyword, f"{title} {contents}"):
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
