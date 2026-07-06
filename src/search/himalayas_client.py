"""Himalayas public API — free, no key, remote-only postings.

Queries the **search** endpoint (``/jobs/api/search``) once per keyword with
``q={keyword}&country=US``, NOT the bare browse feed (``/jobs/api``). Why:
  * The browse feed is unfiltered — ~45% of a page is region-locked NON-US
    postings (UK/Canada/India/Philippines; measured 9/20 on 2026-07-02), which
    are false positives for a US remote seeker (the marketing-remote persona's
    #1 gap). ``search?country=US`` returns only US-eligible rows (0/20 non-US-
    only, same measurement) and honors a server-side ``q=`` keyword filter.
  * The search endpoint IGNORES ``offset`` (it returns a fixed relevance-ranked
    top slice per query — verified live), so we do ONE request per keyword and
    do not page. The old browse client's 100-deep tail contributed ~0 matches in
    practice anyway, so nothing useful is lost. ``parallel_keywords`` makes the
    engine call ``search()`` once per keyword.

ATTRIBUTION / ToS (research-sources §F): Himalayas requires attribution + a
link BACK, and PROHIBITS re-submitting its jobs to Jooble/Google-Jobs/LinkedIn.
This client preserves the Himalayas link as the job URL (``applicationLink`` ->
``guid`` fallback, both himalayas.app links) and NEVER forwards its rows
anywhere — each source client queries its own API independently; no cross-source
forwarding path exists (pinned by test_himalayas_no_jooble_forwarding).

Quirks handled here: pubDate is a UNIX timestamp (int) and must become an
ISO string for search_engine._parse_created; minSalary/maxSalary come with
a salaryPeriod ("yearly"/"monthly"/"hourly") that needs annualizing."""
import hashlib
from datetime import datetime, timezone
from typing import Optional

from config import (
    HIMALAYAS_COUNTRY,
    HIMALAYAS_PAGE_SIZE,
    HIMALAYAS_RATE_LIMIT,
    HIMALAYAS_SEARCH_URL,
)
from models import JobResult
from search.http_util import cache_key
from search.single_feed_client import SingleFeedClient

# salaryPeriod -> multiplier to annualize
_PERIOD_FACTOR = {
    "yearly": 1,
    "annual": 1,      # value actually returned by the API
    "annually": 1,
    "monthly": 12,
    "weekly": 52,
    "daily": 260,
    "hourly": 2080,
}


def _annualize(value, period: str) -> Optional[int]:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    amount *= _PERIOD_FACTOR.get((period or "yearly").lower(), 1)
    # Same sanity bounds as match.scorer's salary recovery.
    if 30_000 <= amount <= 500_000:
        return int(amount)
    return None


def _iso_from_unix(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _job_id(guid: str, url: str, title: str, company: str) -> str:
    """Stable per-posting id. Himalayas often returns an empty ``guid``, which
    used to collapse every such job to the bare prefix ``"himalayas_"`` (a single
    dedup bucket). Fall back to an md5 of the URL, or of ``title|company`` when
    even the URL is missing, so distinct postings stay distinct."""
    if guid:
        return f"himalayas_{guid}"
    seed = url or f"{title}|{company}"
    return f"himalayas_{hashlib.md5(seed.encode('utf-8')).hexdigest()}"


class HimalayasClient(SingleFeedClient):
    cache_subdir = "himalayas"
    rate_limit = HIMALAYAS_RATE_LIMIT
    # The search endpoint filters server-side per keyword (q=), so query it once
    # per keyword rather than fetching one generic feed and filtering client-side.
    parallel_keywords = True

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        # The search endpoint ignores `offset`/paging (returns a fixed relevance-
        # ranked top slice per query — verified live 2026-07-02), so there is
        # nothing beyond page 1.
        if page > 1:
            return {"jobs": []}
        key = cache_key("himalayas", keyword, HIMALAYAS_COUNTRY)

        def fetch():
            self.limiter.acquire()
            response = self.session.get(
                HIMALAYAS_SEARCH_URL,
                params={
                    "q": keyword,
                    "country": HIMALAYAS_COUNTRY,  # US-eligible only (kills region-locked FPs)
                    "limit": HIMALAYAS_PAGE_SIZE,
                    "offset": 0,
                },
                timeout=30,
            )
            response.raise_for_status()
            return {"jobs": response.json().get("jobs", [])}

        return self._cached(key, fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("jobs", []):
            title = item.get("title", "") or ""
            blob = f"{title} {' '.join(item.get('categories') or [])}"
            if not keyword_matches(source_keyword, blob):
                continue
            desc = self.strip_html(item.get("description", "") or "")
            # Himalayas min/maxSalary are usually null; when a freeform salary
            # string is present, prepend it (BEFORE the 3000-char truncation) so
            # match.scorer.salary_from_text can salvage the range — same trick as
            # remotive_client.
            salary_text = (item.get("salaryDescription")
                           or item.get("salary") or "").strip()
            if salary_text:
                desc = f"Salary: {salary_text}\n{desc}"
            period = item.get("salaryPeriod", "")
            locations = item.get("locationRestrictions") or []
            company = item.get("companyName", "Unknown")
            url = item.get("applicationLink") or item.get("guid", "")
            results.append(JobResult(
                title=title,
                company=company,
                location=", ".join(locations) if locations else "Remote",
                salary_min=_annualize(item.get("minSalary"), period),
                salary_max=_annualize(item.get("maxSalary"), period),
                description=desc[:3000],
                url=url,
                source_keyword=source_keyword,
                created=_iso_from_unix(item.get("pubDate")),
                job_id=_job_id(item.get("guid", ""), url, title, company),
                source_api="himalayas",
            ))
        return results
