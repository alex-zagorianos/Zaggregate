"""Breezy HR careers scraper (Tier-1 simple/list style, mirrors rippling).

Endpoint (public, no auth):
    GET https://{slug}.breezy.hr/json?verbose=true  ->  [ {job}, ... ]

`slug` is the tenant subdomain. Job shape (validated live 2026-07-01 against
breezy.breezy.hr): a top-level list; each job carries `id`, `friendly_id`,
`name` (title), `url`, `published_date`, `location` (a dict or string),
`department`, `description` (HTML), `company`.

Routed through careers_session + per-host limiter + conditional_get; fail-soft -> [].
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
from scrape._log import diag
from search.http_util import careers_host_limiter, careers_session, host_of

_BASE_URL = "https://{slug}.breezy.hr/json?verbose=true"
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _clean(raw: str) -> str:
    return strip_html_to_text(raw)


def _field(v) -> str:
    """A Breezy location sub-field may be a plain string OR a {'name': ...} dict."""
    if isinstance(v, dict):
        return (v.get("name") or "").strip()
    if isinstance(v, str):
        return v.strip()
    return ""


def _location(job: dict) -> str:
    loc = job.get("location")
    if isinstance(loc, dict):
        name = _field(loc.get("name"))
        city = _field(loc.get("city"))
        state = _field(loc.get("state"))
        country = _field(loc.get("country"))
        parts = [p for p in (city, state) if p]
        if parts:
            return ", ".join(parts)
        if name:
            return name
        if country:
            return country
        if loc.get("is_remote"):
            return "Remote"
    if isinstance(loc, str) and loc.strip():
        return loc.strip()
    return ""


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False) -> list[JobResult]:
    url = _BASE_URL.format(slug=slug)
    cache_file = ((cache_dir or CACHE_DIR) / f"breezy_{slug_safe(slug)}.json"
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
            diag(f"  [breezy] {slug}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            diag(f"  [breezy] {slug}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _map(result.body, slug, keyword)

    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, headers=_HEADERS,
                                     timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        diag(f"  [breezy] {slug}: error — {e}")
        return []
    return _map(data, slug, keyword)


def _map(data, slug: str, keyword: str) -> list[JobResult]:
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except Exception:
            return []
    jobs = data if isinstance(data, list) else (data.get("jobs", []) if isinstance(data, dict) else [])
    jobs = jobs or []
    out: list[JobResult] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = job.get("name", "") or ""
        dept = job.get("department", "") or ""
        if isinstance(dept, dict):
            dept = dept.get("name", "") or ""
        desc = _clean(job.get("description", "") or "")
        if dept:
            desc = (desc + " " + dept).strip()
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, desc):
                continue
        raw_company = job.get("company")
        if isinstance(raw_company, dict):
            raw_company = raw_company.get("name") or ""
        company = (raw_company or "").strip() or slug.replace("-", " ").title()
        jid = job.get("id") or job.get("friendly_id") or ""
        out.append(JobResult(
            title=title,
            company=company,
            location=_location(job),
            salary_min=None,
            salary_max=None,
            description=desc,
            url=(job.get("url") or "").strip(),
            source_keyword="",
            created=job.get("published_date") or job.get("creation_date") or "",
            job_id=f"breezy_{jid}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
