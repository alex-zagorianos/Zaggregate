"""LinkedIn LOGGED-OUT GUEST endpoint only (spec §2/§3).

Public, unauthenticated job-card fragment — NO login, NO cookies, NO accounts.
Off by default; the user opts in via --sources linkedin_guest. Conservative
rate limit. The guest endpoint returns an HTML fragment of job cards, parsed
with BeautifulSoup (html.parser).
"""
from typing import Optional

from bs4 import BeautifulSoup

from config import LINKEDIN_GUEST_PAGE_SIZE, LINKEDIN_GUEST_RATE_LIMIT, LINKEDIN_GUEST_URL
from models import JobResult
from search.http_util import cache_key
from search.single_feed_client import SingleFeedClient


class LinkedInGuestClient(SingleFeedClient):
    cache_subdir = "linkedin_guest"
    rate_limit = LINKEDIN_GUEST_RATE_LIMIT
    user_agent = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

    def search(self, keyword: str, location: str = "", salary_min: Optional[int] = None,
               page: int = 1) -> dict:
        start = (page - 1) * LINKEDIN_GUEST_PAGE_SIZE
        key = cache_key("linkedin_guest", keyword, location, start)

        def fetch():
            self.limiter.acquire()
            resp = self.session.get(LINKEDIN_GUEST_URL, params={
                "keywords": keyword, "location": location, "start": start,
            }, timeout=30)
            resp.raise_for_status()
            return {"html": resp.text}

        return self._cached(key, fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        html = raw.get("html") or ""
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for card in soup.select("li div.base-card, div.base-card"):
            def _txt(sel):
                el = card.select_one(sel)
                return el.get_text(strip=True) if el else ""
            title = _txt("h3.base-search-card__title")
            if not title:
                continue
            link_el = card.select_one("a.base-card__full-link")
            url = (link_el.get("href") if link_el else "") or ""
            time_el = card.select_one("time.job-search-card__listdate")
            created = (time_el.get("datetime") if time_el else "") or ""
            results.append(JobResult(
                title=title,
                company=_txt("h4.base-search-card__subtitle") or "Unknown",
                location=_txt("span.job-search-card__location"),
                salary_min=None,
                salary_max=None,
                description="",
                url=url.split("?")[0],
                source_keyword=source_keyword,
                created=created,
                job_id=f"linkedin_{url.rstrip('/').split('/')[-1]}" if url else "",
                source_api="linkedin_guest",
            ))
        return results
