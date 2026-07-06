"""Paylocity Recruiting careers-feed scraper (Tier-1 simple/list style, mirrors
rippling/bamboohr).

Endpoint (OFFICIALLY documented public feed --
recruiting.paylocity.com/Recruiting/v2/api/feed/documentation):
    GET https://recruiting.paylocity.com/recruiting/v2/api/feed/jobs/{companyGuid}
      -> {"displayName": "...", "jobs": [ {job}, ... ]}

The company GUID appears in a Paylocity careers URL:
    recruiting.paylocity.com/recruiting/jobs/All/{guid}/...
so `slug` for a paylocity CompanyEntry is that GUID.

Response shape (per the documentation, confirmed 2026-07-01 against the live
doc page): each job carries `jobId`, `title`, `description`/`requirements`
(HTML), `hiringDepartment`, `jobLocation` (an address object with
`locationDisplayName`/`city`/`state`), `applyUrl`/`displayUrl`, `createdUtc`,
`publishedDate`. All fields read defensively via .get() because tenants vary.

Routed through the shared careers_session + per-host limiter + conditional_get,
identical to the other careers scrapers, so a throttled feed is served stale and
never poisoned. Network/parse errors fail-soft -> [].
"""
import json
from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import (
    STATUS_PERMANENT, conditional_get, http_cache_body, is_failed, mark_failed,
    read_cache, slug_safe,
)
from scrape.html_text import strip_html_to_text
from search.http_util import careers_host_limiter, careers_session, host_of

_BASE_URL = "https://recruiting.paylocity.com/recruiting/v2/api/feed/jobs/{guid}"
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _clean(raw: str) -> str:
    return strip_html_to_text(raw)


def _location(job: dict) -> str:
    """Best location string from a Paylocity jobLocation address object."""
    loc = job.get("jobLocation")
    if isinstance(loc, dict):
        disp = (loc.get("locationDisplayName") or "").strip()
        if disp:
            return disp
        parts = [p for p in ((loc.get("city") or "").strip(),
                             (loc.get("state") or "").strip()) if p]
        if parts:
            return ", ".join(parts)
        for k in ("name", "metro", "zip"):
            v = (loc.get(k) or "").strip()
            if v:
                return v
    # Some tenants flatten a bare string location.
    if isinstance(loc, str) and loc.strip():
        return loc.strip()
    return ""


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False) -> list[JobResult]:
    url = _BASE_URL.format(guid=slug)
    cache_file = ((cache_dir or CACHE_DIR) / f"paylocity_{slug_safe(slug)}.json"
                  if cache_enabled else None)

    if cache_enabled and cache_file is not None:
        cached = read_cache(cache_file)
        if is_failed(cached):
            return []
        if cached is not None:
            return _map(http_cache_body(cached), slug, keyword)

        careers_host_limiter(host_of(url)).acquire()
        result = conditional_get(url, cache_file, headers=_HEADERS,
                                 timeout=CAREERS_REQUEST_TIMEOUT,
                                 session=careers_session())
        if result.status == STATUS_PERMANENT:
            print(f"  [paylocity] {slug}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            print(f"  [paylocity] {slug}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _map(result.body, slug, keyword)

    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, headers=_HEADERS,
                                     timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [paylocity] {slug}: error — {e}")
        return []
    return _map(data, slug, keyword)


def _map(data, slug: str, keyword: str) -> list[JobResult]:
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except Exception:
            return []
    if not isinstance(data, dict):
        return []
    company = (data.get("displayName") or "").strip() or slug.replace("-", " ").title()
    jobs = data.get("jobs", []) or []
    out: list[JobResult] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = job.get("title", "") or ""
        dept = job.get("hiringDepartment", "") or ""
        desc = _clean(job.get("description", "") or "")
        req = _clean(job.get("requirements", "") or "")
        blob = (desc + " " + req).strip()
        if dept:
            blob = (blob + " " + dept).strip()
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, blob):
                continue
        job_id = job.get("jobId", "") or ""
        url = (job.get("displayUrl") or job.get("applyUrl") or "").strip()
        out.append(JobResult(
            title=title,
            company=company,
            location=_location(job),
            salary_min=None,
            salary_max=None,
            description=blob[:3000],
            url=url,
            source_keyword="",
            created=job.get("publishedDate") or job.get("createdUtc") or "",
            job_id=f"paylocity_{job_id}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
