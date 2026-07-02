"""EdJoin — "the nation's #1 education job board" — via its PUBLIC JSON search
endpoint. Free, no key, no login. The ToS-safe K-12 channel that routes around
Frontline/AppliTrack (no clean feed) and NEOGOV (ToS-blocked, never scrape).

We call the SAME endpoint EdJoin's own anonymous (not-signed-in) browser client
uses — discovered live 2026-07-02 by reading /Scripts/pages/jobs.js:
``getJobsData()`` GETs ``/Home/LoadJobs`` (the signed-in variant is
``LoadJobsSignedIn`` — we always use the public one) with the query string that
``buildSearchQueryString()`` assembles. This is a JSON endpoint, so NO HTML
parsing is needed:

    GET https://www.edjoin.org/Home/LoadJobs?rows=..&page=1&sort=postingDate&
        order=desc&keywords={kw}&location=&searchType=all&...(numeric IDs=0)
    -> {"totalRecords", "totalPages", "totalOpenings", "data": [ {posting}, ... ]}

Each posting row carries positionTitle, districtName, city, stateName, postingID
(-> /Home/JobPosting/{id}), postingDate (MS "/Date(ms)/"), and salary fields
(beginningSalary/endingSalary or PayRangeFrom/PayRangeTo). Verified live: a bare
``keywords=teacher`` search returns 9,260+ real CA K-12 postings.

ROBOTS/ToS: edjoin.org serves NO robots.txt (HTTP 404 on both hosts, checked
live 2026-07-02) → no crawl restrictions declared. The listings are public with
no login wall, and LoadJobs is the site's own published-jobs read path. We query
it politely: one server-side-filtered request per keyword, rows-capped, cached
once per cycle.

CALIFORNIA-CENTRIC: EdJoin is overwhelmingly California (the "location" query
param does NOT filter — filtering is by stateID/regionID or client-side on the
result city/state). We metro-localize the results via remote_intent like the
other sector feeds; for a NON-CA metro no result city matches, so EdJoin
gracefully contributes 0 rows with no noise. A CA metro (LA/SF/San Diego/etc.)
gets localized CA K-12 postings.

INDUSTRY GATING: self-skips unless the active project's industry is an education-
family field (shared _EDUCATION_TOKENS gate with HigherEdJobs). Safe to add to
DAILY_SOURCES — inert for every non-education field.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from models import JobResult
from search.higheredjobs_client import _EDUCATION_TOKENS
from search.http_util import cache_key
from search.single_feed_client import SingleFeedClient

EDJOIN_LOADJOBS_URL = "https://www.edjoin.org/Home/LoadJobs"
EDJOIN_JOB_URL = "https://www.edjoin.org/Home/JobPosting/{posting_id}"
EDJOIN_RATE_LIMIT = 5
EDJOIN_ROWS = 25  # per-keyword result cap (polite; the endpoint returns ~this many)

# ASP.NET "/Date(ms)/" (optionally with a +0000 offset) -> epoch ms.
_MS_DATE_RE = re.compile(r"/Date\((-?\d+)")

# Salary sanity bounds (mirror match.scorer / himalayas annualization).
_SAL_MIN, _SAL_MAX = 20_000, 500_000


def _is_education(industry: Optional[str]) -> bool:
    """True when the industry is an education-family field (shared gate with
    HigherEdJobs). Empty/eng default -> False (inert)."""
    import industry_profile
    toks = set(industry_profile._tokens(industry or ""))
    return bool(toks & _EDUCATION_TOKENS)


def _iso_from_ms_date(value) -> str:
    """ASP.NET '/Date(1782950400000)/' -> ISO-8601 UTC string. Bad/empty -> ''."""
    if not value:
        return ""
    m = _MS_DATE_RE.search(str(value))
    if not m:
        return ""
    try:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _num(value) -> Optional[int]:
    """Parse a salary-ish value to an int within sane annual bounds, else None.
    Handles '55000', '55,000.00', 55000, and rejects hourly/blank/garbage."""
    if value is None:
        return None
    s = re.sub(r"[^\d.]", "", str(value))
    if not s:
        return None
    try:
        amount = float(s)
    except ValueError:
        return None
    if _SAL_MIN <= amount <= _SAL_MAX:
        return int(amount)
    return None


def _salary(row: dict) -> tuple[Optional[int], Optional[int]]:
    """(min, max) annual from a posting, preferring the explicit range fields.
    EdJoin frequently leaves these null (salary in free-text salaryInfo), so this
    returns (None, None) more often than not — that's fine, the scorer can still
    salvage from the description."""
    lo = _num(row.get("beginningSalary")) or _num(row.get("PayRangeFrom"))
    hi = _num(row.get("endingSalary")) or _num(row.get("PayRangeTo"))
    return lo, hi


def _location_of(row: dict) -> str:
    """"City, ST" from a posting (stateName -> 2-letter via search_engine table)."""
    city = (row.get("city") or "").strip()
    state_name = (row.get("stateName") or "").strip()
    if not state_name:
        return city
    from search.search_engine import _STATE_ABBREVS
    ab = _STATE_ABBREVS.get(state_name.lower(), "")
    st = ab.upper() if ab else state_name
    if city and st:
        return f"{city}, {st}"
    return city or st


class EdjoinClient(SingleFeedClient):
    cache_subdir = "edjoin"
    rate_limit = EDJOIN_RATE_LIMIT
    # LoadJobs filters server-side per keyword, so query it once per keyword.
    parallel_keywords = True
    # EdJoin is behind an IIS app that 500s a bare/unbrowser-like request; use a
    # browser-ish UA + XHR header like its own client does.
    user_agent = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

    def __init__(self, cache_dir=None, cache_enabled: bool = True,
                 industry: Optional[str] = None, location: Optional[str] = None):
        super().__init__(cache_dir=cache_dir, cache_enabled=cache_enabled)
        if industry is None:
            try:
                from search.source_taxonomy import active_industry
                industry = active_industry()
            except Exception:
                industry = ""
        self.industry = industry or ""
        self.location = location or ""
        self.active = _is_education(self.industry)
        self.session.headers["X-Requested-With"] = "XMLHttpRequest"
        self.session.headers["Accept"] = "application/json, text/javascript, */*"

    def _params(self, keyword: str) -> dict:
        # The endpoint NPEs on missing params, so send the full set the site's own
        # buildSearchQueryString() sends, with its default values (verified live).
        # location='' (does NOT filter — filtering is client-side on the result
        # city/state) and all numeric IDs 0.
        return {
            "rows": EDJOIN_ROWS, "page": 1,
            "sort": "postingDate", "sortVal": 0, "order": "desc",
            "keywords": keyword, "location": "", "searchType": "all",
            "regions": "", "jobTypes": "", "days": 0, "empType": "",
            "catID": 0, "onlineApps": "", "recruitmentCenterID": 0,
            "stateID": 0, "regionID": 0, "districtID": 0, "searchID": 0,
        }

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        if page > 1 or not self.active:
            return {"data": [], "_location": location or ""}
        key = cache_key("edjoin", keyword)

        def fetch():
            self.limiter.acquire()
            resp = self.session.get(EDJOIN_LOADJOBS_URL, params=self._params(keyword),
                                    timeout=30)
            resp.raise_for_status()
            try:
                payload = resp.json()
            except ValueError:
                return {"data": []}  # server returned an HTML error page -> no rows
            return {"data": payload.get("data", []) or []}

        raw = self._cached(key, fetch)
        raw["_location"] = location or ""
        return raw

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        from search.remote_intent import (
            is_remote_only, metro_variant_set, remote_region_of,
            tag_nationwide_remote)
        search_loc = raw.get("_location", "") or ""
        remote = is_remote_only(search_loc)
        region = remote_region_of(search_loc) if remote else None
        metro_variants = None
        if search_loc and not remote:
            mv = metro_variant_set(search_loc)
            metro_variants = mv or None
        # EdJoin is a California-wide feed. When the user targets a CA metro but
        # the (narrow, CBSA-principal-city) metro filter matches no exact-city
        # rows, fall back to statewide CA rather than return 0 — a CA teacher
        # legitimately wants CA K-12 jobs. For a NON-CA target, we keep the strict
        # metro filter, which yields 0 (no CA city matches an OH/TX metro) — the
        # required "graceful 0 for a non-covered metro". Detect a CA target from
        # the search location's state token.
        target_is_ca = _target_state_is_ca(search_loc)
        metro_rows: list[JobResult] = []
        all_rows: list[JobResult] = []
        for row in raw.get("data", []) or []:
            title = (row.get("positionTitle") or "").strip()
            if not title:
                continue
            # The endpoint already keyword-filtered server-side; re-check on the
            # title + jobType so a broadened API keyword doesn't leak off-target
            # rows into a narrow scoring keyword.
            blob = f"{title} {row.get('jobType') or ''}"
            if not keyword_matches(source_keyword, blob):
                continue
            location = _location_of(row)
            in_metro = True
            if remote:
                location = tag_nationwide_remote(location, region)
            elif metro_variants is not None:
                low = (location or "").lower()
                is_remote_row = "remote" in low
                in_metro = (not location) or is_remote_row or any(
                    v in low for v in metro_variants)
            posting_id = row.get("postingID")
            url = (EDJOIN_JOB_URL.format(posting_id=posting_id)
                   if posting_id not in (None, "", 0) else "")
            lo, hi = _salary(row)
            job = JobResult(
                title=title,
                company=(row.get("districtName") or "Unknown").strip() or "Unknown",
                location=location,
                salary_min=lo,
                salary_max=hi,
                description=(row.get("salaryInfo") or "").strip()[:3000],
                url=url,
                source_keyword=source_keyword,
                created=_iso_from_ms_date(row.get("postingDate")),
                job_id=f"edjoin_{posting_id}" if posting_id else "",
                source_api="edjoin",
            )
            all_rows.append(job)
            if in_metro:
                metro_rows.append(job)
        if metro_rows:
            return metro_rows
        # No exact-metro hits: statewide-CA fallback only for a CA target (else 0).
        return all_rows if target_is_ca else []


def _target_state_is_ca(location: Optional[str]) -> bool:
    """True when the search location names California (so EdJoin may fall back to
    statewide-CA). A non-CA / bare-city / empty target -> False (strict metro
    filter, i.e. graceful 0 for a non-CA metro)."""
    loc = (location or "").strip().lower()
    if not loc:
        return False
    toks = [t.strip().rstrip(",.") for t in loc.replace(",", " ").split()]
    return "ca" in toks or "california" in loc
