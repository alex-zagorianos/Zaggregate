"""Pinpoint HQ careers scraper (Tier-1 simple/list style, mirrors rippling).

Endpoint (public, no auth; must send X-Requested-With: XMLHttpRequest):
    GET https://{slug}.pinpointhq.com/postings.json  ->  {"data": [ {job}, ... ]}

`slug` is the tenant subdomain. Job shape (validated live 2026-07-01 against
workwithus.pinpointhq.com): jobs under `data`; each carries `id`, `title`,
`url`, `path`, `description` (HTML), `location` (a dict with city/province/name),
`employment_type_text`, compensation fields.

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

_BASE_URL = "https://{slug}.pinpointhq.com/postings.json"
_HEADERS = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _clean(raw: str) -> str:
    return strip_html_to_text(raw)


def _location(job: dict) -> str:
    loc = job.get("location")
    if isinstance(loc, dict):
        city = (loc.get("city") or "").strip()
        prov = (loc.get("province") or "").strip()
        name = (loc.get("name") or "").strip()  # often the country
        parts = [p for p in (city, prov) if p]
        if parts:
            return ", ".join(parts)
        if name:
            return name
    if isinstance(loc, str) and loc.strip():
        return loc.strip()
    wt = (job.get("workplace_type_text") or "").strip()
    return wt


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False) -> list[JobResult]:
    url = _BASE_URL.format(slug=slug)
    cache_file = ((cache_dir or CACHE_DIR) / f"pinpoint_{slug_safe(slug)}.json"
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
            diag(f"  [pinpoint] {slug}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            diag(f"  [pinpoint] {slug}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _map(result.body, slug, keyword)

    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, headers=_HEADERS,
                                     timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        diag(f"  [pinpoint] {slug}: error — {e}")
        return []
    return _map(data, slug, keyword)


def _map(data, slug: str, keyword: str) -> list[JobResult]:
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except Exception:
            return []
    if isinstance(data, list):
        jobs = data
    elif isinstance(data, dict):
        jobs = data.get("data", []) or []
    else:
        jobs = []
    out: list[JobResult] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = job.get("title", "") or ""
        etype = (job.get("employment_type_text") or "").strip()
        desc = _clean(job.get("description", "") or "")
        if etype:
            desc = (desc + " " + etype).strip()
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, desc):
                continue
        jid = job.get("id") or ""
        job_url = (job.get("url") or "").strip()
        if not job_url and job.get("path"):
            job_url = f"https://{slug}.pinpointhq.com{job['path']}"
        out.append(JobResult(
            title=title,
            company=slug.replace("-", " ").title(),
            location=_location(job),
            salary_min=None,
            salary_max=None,
            description=desc,
            url=job_url,
            source_keyword="",
            created=job.get("created_at") or job.get("published_at") or "",
            job_id=f"pinpoint_{jid}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
