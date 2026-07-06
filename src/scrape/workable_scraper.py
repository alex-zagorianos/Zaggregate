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

_BASE_URL = "https://apply.workable.com/api/v1/widget/accounts/{slug}"
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _clean(raw: str) -> str:
    return strip_html_to_text(raw)


def _location(loc: dict) -> str:
    parts = [loc.get("city"), loc.get("region"), loc.get("country")]
    return ", ".join(p for p in parts if p)


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False) -> list[JobResult]:
    url = _BASE_URL.format(slug=slug)
    cache_file = ((cache_dir or CACHE_DIR) / f"workable_{slug_safe(slug)}.json"
                  if cache_enabled else None)

    if cache_enabled and cache_file is not None:
        cached = read_cache(cache_file)
        if is_failed(cached):
            return []  # known-dead this TTL window
        if cached is not None:
            return _map(http_cache_body(cached), slug, keyword)

        careers_host_limiter(host_of(url)).acquire()
        result = conditional_get(url, cache_file, headers=_HEADERS,
                                 timeout=CAREERS_REQUEST_TIMEOUT,
                                 session=careers_session())
        if result.status == STATUS_PERMANENT:
            diag(f"  [workable] {slug}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            diag(f"  [workable] {slug}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _map(result.body, slug, keyword)

    # --no-cache: plain fetch, nothing persisted.
    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, headers=_HEADERS,
                                     timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        diag(f"  [workable] {slug}: error — {e}")
        return []
    return _map(data, slug, keyword)


def _map(data: dict, slug: str, keyword: str) -> list[JobResult]:
    company = data.get("name") or slug.replace("-", " ").title()
    jobs = data.get("jobs", []) or []
    out: list[JobResult] = []
    for job in jobs:
        title = job.get("title", "") or ""
        body = _clean(job.get("description", ""))
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, body):
                continue
        out.append(JobResult(
            title=title,
            company=company,
            location=_location(job.get("location") or {}),
            salary_min=None,
            salary_max=None,
            description=body,
            url=job.get("url") or "",
            source_keyword="",
            created=job.get("published_on") or "",
            job_id=f"workable_{job.get('shortcode', '')}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
