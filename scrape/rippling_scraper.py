from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import (
    STATUS_PERMANENT, conditional_get, http_cache_body, is_failed, mark_failed,
    read_cache, slug_safe,
)
from search.http_util import careers_host_limiter, careers_session, host_of

_BASE_URL = "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs"
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False) -> list[JobResult]:
    url = _BASE_URL.format(slug=slug)
    cache_file = ((cache_dir or CACHE_DIR) / f"rippling_{slug_safe(slug)}.json"
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
            print(f"  [rippling] {slug}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            print(f"  [rippling] {slug}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _map(result.body, slug, keyword)

    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, headers=_HEADERS,
                                     timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [rippling] {slug}: error — {e}")
        return []
    return _map(data, slug, keyword)


def _map(data, slug: str, keyword: str) -> list[JobResult]:
    jobs = data if isinstance(data, list) else data.get("items", []) or []
    out: list[JobResult] = []
    for j in jobs:
        loc = (j.get("workLocation") or {}).get("label") or ""
        dept = (j.get("department") or {}).get("label") or ""
        desc = (j.get("description") or "")[:3000]
        if dept:
            desc = (desc + " " + dept).strip()
        title = j.get("name", "") or ""
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, desc):
                continue
        out.append(JobResult(
            title=title,
            company=slug.replace("-", " ").title(),
            location=loc,
            salary_min=None,
            salary_max=None,
            description=desc,
            url=j.get("url") or "",
            source_keyword="",
            created=j.get("createdAt") or j.get("postedDate") or "",
            job_id=f"rippling_{j.get('id', '')}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
