"""CareerOneStop (US DOL / NLx) job search — the single biggest free reach win
for non-technical users (review P1 Tier A #1).

Backed by the National Labor Exchange: ~3.5M active US jobs/day aggregated from
all 50 state job banks + ~300k employers (nurses, teachers, trades, retail,
state/local government). Free key required — a userId + API token from
careeronestop.org/Developers/WebAPI/registration.aspx. Key-gated exactly like
adzuna/usajobs: a missing credential raises ValueError so build_clients() catches
it and prints a one-line skip (the daily run stays byte-identical for a keyless
user).

Endpoint (all segments are PATH parameters, URL-encoded):

    GET {BASE}/{userId}/{keyword}/{location}/{radius}/{sortColumns}/{sortOrder}/
        {startRecord}/{pageSize}/{days}
    Authorization: Bearer {token}

Response shape (from the CareerOneStop API explorer / list-jobs docs):

    {"Jobs": [{"JvId", "JobTitle", "Company", "Location", "URL",
               "AccquisitionDate", ...}], "RecordCount": N, ...}

NOTE (provisional field mapping): the official docs pages (list-jobs.aspx,
technical-information.aspx) returned 403/500 to automated fetch on 2026-07-01, so
the per-job field names below are derived from the CareerOneStop API-explorer
listing rather than a captured live payload. The parser reads several plausible
aliases per field so a minor casing/spelling difference (their 'AccquisitionDate'
is misspelled upstream) does not silently drop data. Verify against one live
response before relying on salary/description fields.

The required attribution string lives in config.CAREERONESTOP_ATTRIBUTION and is
surfaced by the UI layer (not this client's job).
"""
import re
from typing import Optional
from urllib.parse import quote

import config
from config import (
    CAREERONESTOP_BASE_URL,
    CAREERONESTOP_DAYS,
    CAREERONESTOP_RADIUS,
    CAREERONESTOP_RATE_LIMIT,
    CAREERONESTOP_RESULTS_PER_PAGE,
)
from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, cache_key, make_session, to_float
from pathlib import Path

# Required by the US DOL terms of use; re-exported so callers can display it
# without importing config directly.
ATTRIBUTION = config.CAREERONESTOP_ATTRIBUTION

_TAG_RE = re.compile(r"<[^>]+>")


def _seg(value) -> str:
    """URL-encode a single path segment. A blank required segment is replaced by
    '0' (CareerOneStop's documented 'no filter' sentinel for keyword/location),
    and '/' is fully escaped so a location like 'Cincinnati, OH' can't split the
    path."""
    s = str(value).strip()
    if not s:
        return "0"
    return quote(s, safe="")


class CareerOneStopClient(JobAPIClient):
    # Keyword-parameterized + stateless across keywords -> SearchEngine may fetch
    # each keyword concurrently (see search_engine.run_full_search).
    parallel_keywords = True

    def __init__(
        self,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        radius: Optional[int] = None,
        days: Optional[int] = None,
    ):
        # Re-resolve env-then-secret at construction (config constants froze at
        # import) so a key pasted into the in-app box is honored. Explicit args
        # still win for tests.
        self.user_id = user_id or config.resolve_secret(
            "CAREERONESTOP_USER_ID", "careeronestop_user_id")
        self.token = token or config.resolve_secret(
            "CAREERONESTOP_TOKEN", "careeronestop_token")
        if not self.user_id or not self.token:
            raise ValueError(
                "CareerOneStop credentials missing. Set CAREERONESTOP_USER_ID and "
                "CAREERONESTOP_TOKEN in .env (free key at "
                "careeronestop.org/Developers/WebAPI/registration.aspx)."
            )
        self.radius = radius if radius is not None else CAREERONESTOP_RADIUS
        self.days = days if days is not None else CAREERONESTOP_DAYS
        self.cache = FileCache("careeronestop", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.limiter = RateLimiter(CAREERONESTOP_RATE_LIMIT)

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        # startRecord is 1-based; pageSize rows per page.
        page = max(1, page)
        start_record = (page - 1) * CAREERONESTOP_RESULTS_PER_PAGE + 1
        key = cache_key("careeronestop", keyword, location, self.radius,
                        self.days, start_record)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        self.limiter.acquire()

        url = "/".join([
            CAREERONESTOP_BASE_URL.rstrip("/"),
            _seg(self.user_id),
            _seg(keyword),
            _seg(location),
            _seg(self.radius),
            "0",                 # sortColumns: 0 = default (relevance)
            "0",                 # sortOrder:   0 = default
            str(start_record),
            str(CAREERONESTOP_RESULTS_PER_PAGE),
            _seg(self.days),
        ])
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        response = self.session.get(url, headers=headers, timeout=30)
        # CareerOneStop returns 404 when a query simply has no matches (not an
        # error). Treat it as an empty result set rather than raising.
        if response.status_code == 404:
            data = {"Jobs": [], "RecordCount": 0}
        else:
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError:
                data = {"Jobs": [], "RecordCount": 0}

        if self.cache_enabled:
            self.cache.put(key, data)
        return data

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        # Their JSON key is "Jobs"; accept a couple of harmless aliases so a case
        # difference upstream doesn't zero the source out.
        items = raw.get("Jobs") or raw.get("jobs") or raw.get("JobList") or []
        for item in items:
            if not isinstance(item, dict):
                continue
            jv_id = item.get("JvId") or item.get("JvID") or item.get("Id") or ""
            title = item.get("JobTitle") or item.get("Title") or "Unknown"
            company = item.get("Company") or item.get("CompanyName") or "Unknown"
            location = item.get("Location") or item.get("JobLocation") or ""
            url = item.get("URL") or item.get("Url") or item.get("JobURL") or ""
            # Upstream misspells "Acquisition"; read both plus a couple of aliases.
            created = (item.get("AccquisitionDate") or item.get("AcquisitionDate")
                       or item.get("DatePosted") or item.get("PostedDate") or "")
            description = _TAG_RE.sub(
                " ", item.get("Description") or item.get("JobDescription") or "")
            salary_min = to_float(item.get("SalaryMin") or item.get("MinSalary"))
            salary_max = to_float(item.get("SalaryMax") or item.get("MaxSalary"))
            results.append(
                JobResult(
                    title=title or "Unknown",
                    company=company or "Unknown",
                    location=location or "",
                    salary_min=salary_min,
                    salary_max=salary_max,
                    description=(description or "")[:3000],
                    url=url or "",
                    source_keyword=source_keyword,
                    created=created or "",
                    job_id=f"careeronestop_{jv_id}" if jv_id else "",
                    source_api="careeronestop",
                )
            )
        return results
