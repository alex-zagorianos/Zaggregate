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

_BASE_URL = "https://{slug}.recruitee.com/api/offers/"
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _clean(raw: str) -> str:
    return strip_html_to_text(raw)


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False) -> list[JobResult]:
    url = _BASE_URL.format(slug=slug)
    cache_file = ((cache_dir or CACHE_DIR) / f"recruitee_{slug_safe(slug)}.json"
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
            print(f"  [recruitee] {slug}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            print(f"  [recruitee] {slug}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _map(result.body, slug, keyword)

    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, headers=_HEADERS,
                                     timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [recruitee] {slug}: error — {e}")
        return []
    return _map(data, slug, keyword)


def _map(data: dict, slug: str, keyword: str) -> list[JobResult]:
    offers = data.get("offers", []) or []
    out: list[JobResult] = []
    for o in offers:
        title = o.get("title", "") or ""
        body = _clean(o.get("description", ""))
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, body):
                continue
        loc = ", ".join(p for p in (o.get("city"), o.get("country")) if p)
        out.append(JobResult(
            title=title,
            company=o.get("company_name") or slug.replace("-", " ").title(),
            location=loc,
            salary_min=None,
            salary_max=None,
            description=body,
            url=o.get("careers_url") or "",
            source_keyword="",
            created=o.get("published_at") or "",
            job_id=f"recruitee_{o.get('id', '')}",
            source_api="careers",
            board_count=len(offers),
        ))
    return out
