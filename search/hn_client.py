"""Hacker News "Ask HN: Who is hiring?" via the Algolia API — free, no key.

Two-step: (1) find the latest monthly thread posted by the 'whoishiring'
account (cached 24h), (2) per keyword, full-text search that thread's
comments. Top-level comments follow the convention
"Company | Role | Location | ..." on their first line, which we parse for
company/location. Postings skew heavily toward startups and small teams."""
import html
import re
from pathlib import Path
from typing import Optional

from config import HN_ALGOLIA_URL, HN_RATE_LIMIT
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, cache_key, make_session

_TAG_RE = re.compile(r"<[^>]+>")
_BREAK_RE = re.compile(r"<p>|<br\s*/?>", re.IGNORECASE)


def _comment_to_text(comment_html: str) -> str:
    """Algolia returns comment bodies as HTML; convert to plain text with
    paragraph breaks preserved as newlines (the first line carries the
    Company | Role | Location header)."""
    text = _BREAK_RE.sub("\n", comment_html or "")
    text = _TAG_RE.sub(" ", text)
    return html.unescape(text).strip()


def _parse_header(first_line: str) -> tuple[str, str, str]:
    """Split 'Company | Role | Location | ...' -> (company, role, location).
    Missing segments come back empty."""
    parts = [p.strip() for p in first_line.split("|")]
    company = parts[0] if parts else ""
    role = parts[1] if len(parts) > 1 else ""
    location = parts[2] if len(parts) > 2 else ""
    return company, role, location


class HNClient(JobAPIClient):
    def __init__(self, cache_dir: Optional[Path] = None, cache_enabled: bool = True):
        self.cache = FileCache("hn", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.session.headers["User-Agent"] = "JobSearchTool/1.0 (personal use)"
        self.limiter = RateLimiter(HN_RATE_LIMIT, quiet=True)

    def _latest_thread_id(self) -> Optional[str]:
        if self.cache_enabled:
            cached = self.cache.get("thread")
            if cached is not None:
                return cached.get("id")

        self.limiter.acquire()
        response = self.session.get(
            f"{HN_ALGOLIA_URL}/search_by_date",
            params={
                "tags": "story,author_whoishiring",
                "query": "Who is hiring",
                "hitsPerPage": 5,
            },
            timeout=30,
        )
        response.raise_for_status()
        thread_id = None
        for hit in response.json().get("hits", []):
            if "who is hiring" in (hit.get("title") or "").lower():
                thread_id = hit.get("objectID")
                break

        if thread_id and self.cache_enabled:
            self.cache.put("thread", {"id": thread_id})
        return thread_id

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        if page > 1:
            return {"hits": []}

        key = cache_key("hn", keyword)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        thread_id = self._latest_thread_id()
        if not thread_id:
            return {"hits": []}

        self.limiter.acquire()
        response = self.session.get(
            f"{HN_ALGOLIA_URL}/search",
            params={
                "tags": f"comment,story_{thread_id}",
                "query": keyword,
                "hitsPerPage": 100,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = {"hits": response.json().get("hits", [])}

        if self.cache_enabled:
            self.cache.put(key, data)
        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        for hit in raw.get("hits", []):
            text = _comment_to_text(hit.get("comment_text", ""))
            if not text:
                continue
            first_line = text.split("\n", 1)[0]
            company, role, location = _parse_header(first_line)
            # Replies and off-convention comments have no pipes; skip them —
            # only top-level "Company | Role | ..." posts are job ads.
            if "|" not in first_line or not company:
                continue
            comment_id = hit.get("objectID", "")
            results.append(JobResult(
                title=role or first_line[:120],
                company=company,
                location=location or "See posting",
                salary_min=None,
                salary_max=None,
                description=text[:3000],
                url=f"https://news.ycombinator.com/item?id={comment_id}",
                source_keyword=source_keyword,
                created=hit.get("created_at", ""),
                job_id=f"hn_{comment_id}",
                source_api="hn",
            ))
        return results
