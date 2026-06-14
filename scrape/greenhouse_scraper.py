import html
import re
from pathlib import Path
from typing import Optional

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import is_failed, mark_failed, read_cache, slug_safe, write_cache
from scrape.company_registry import CompanyEntry

_BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_content(raw: str) -> str:
    """Greenhouse 'content' is HTML-escaped HTML. Unescape, strip tags, and
    collapse whitespace so the match scorer can read real skill terms from it."""
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", html.unescape(raw))
    return re.sub(r"\s+", " ", text).strip()[:3000]


def scrape_greenhouse(
    company: CompanyEntry,
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
) -> list[JobResult]:
    cache_file = cache_dir / f"greenhouse_{slug_safe(company.slug)}.json"

    if cache_enabled:
        cached = read_cache(cache_file)
        if is_failed(cached):
            return []  # known-dead this TTL window
        if cached is not None:
            return _filter_and_map(cached, company, keyword)

    try:
        url = _BASE_URL.format(slug=company.slug)
        resp = requests.get(url, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        print(f"  [greenhouse] {company.name}: HTTP {getattr(e.response, 'status_code', '?')} — skipping")
        if cache_enabled:
            mark_failed(cache_file)
        return []
    except Exception as e:
        print(f"  [greenhouse] {company.name}: error — {e}")
        if cache_enabled:
            mark_failed(cache_file)
        return []

    if cache_enabled:
        write_cache(cache_file, data)

    return _filter_and_map(data, company, keyword)


def _filter_and_map(data: dict, company: CompanyEntry, keyword: str) -> list[JobResult]:
    # Total board size is free here and is a decent company-size proxy.
    total = (data.get("meta") or {}).get("total") or len(data.get("jobs", []))
    results = []
    for job in data.get("jobs", []):
        title = job.get("title", "") or ""
        depts = [d.get("name", "") for d in job.get("departments", [])]
        if not _matches(keyword, title, depts):
            continue

        location = (job.get("location") or {}).get("name") or ""
        results.append(JobResult(
            title=title,
            company=company.name,
            location=location,
            salary_min=None,
            salary_max=None,
            description=_clean_content(job.get("content", "")),
            url=job.get("absolute_url") or "",
            source_keyword=keyword,
            # first_published is the real posting date; updated_at makes big
            # boards that touch postings look perpetually fresh.
            created=job.get("first_published") or job.get("updated_at") or "",
            job_id=f"greenhouse_{job.get('id', '')}",
            source_api="careers",
            board_count=total,
        ))
    return results


def _matches(keyword: str, title: str, departments: list[str]) -> bool:
    from scrape.text_match import keyword_matches
    return keyword_matches(keyword, title + " " + " ".join(departments))
