from datetime import datetime, timezone
from pathlib import Path

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import (
    STATUS_PERMANENT, conditional_get, http_cache_body, is_failed, mark_failed,
    read_cache, slug_safe,
)
from scrape.company_registry import CompanyEntry
from search.http_util import careers_host_limiter, careers_session, host_of

_BASE_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"


def scrape_lever(
    company: CompanyEntry,
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
) -> list[JobResult]:
    cache_file = cache_dir / f"lever_{slug_safe(company.slug)}.json"
    url = _BASE_URL.format(slug=company.slug)

    if cache_enabled:
        # TTL-fresh fast path: unchanged from before this migration, so a
        # second keyword hitting the same company within one run still costs
        # zero network calls. A 304 revalidation below also refreshes this
        # entry's timestamp, keeping that same-run dedup intact.
        cached = read_cache(cache_file)
        if is_failed(cached):
            return []  # known-dead this TTL window
        if cached is not None:
            return _filter_and_map(http_cache_body(cached), company, keyword)

        # TTL-stale (or first-ever) — conditional GET so an unchanged board
        # costs a cheap 304 instead of a full re-download. Shared retry/Retry-
        # After session + per-host limiter so a lever burst can't self-429.
        careers_host_limiter(host_of(url)).acquire()
        result = conditional_get(url, cache_file, timeout=CAREERS_REQUEST_TIMEOUT,
                                 session=careers_session())
        if result.status == STATUS_PERMANENT:
            print(f"  [lever] {company.name}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            print(f"  [lever] {company.name}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _filter_and_map(result.body, company, keyword)

    try:
        resp = requests.get(url, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()  # returns a list, not a dict
    except requests.HTTPError as e:
        print(f"  [lever] {company.name}: HTTP {getattr(e.response, 'status_code', '?')} — skipping")
        return []
    except Exception as e:
        print(f"  [lever] {company.name}: error — {e}")
        return []

    return _filter_and_map(data, company, keyword)


def _filter_and_map(postings: list, company: CompanyEntry, keyword: str) -> list[JobResult]:
    total = len(postings)  # company-size proxy: whole board is in hand
    results = []
    for posting in postings:
        title = posting.get("text", "") or ""
        cats = posting.get("categories", {}) or {}
        team = cats.get("team", "") or ""
        dept = cats.get("department", "") or ""

        # Match on the TITLE only; team/department reach the scorer via the
        # description path below, never the keyword haystack.
        if not _matches(keyword, title):
            continue

        created_ms = posting.get("createdAt")
        if created_ms:
            created = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        else:
            created = ""

        description = (posting.get("descriptionPlain")
                      or posting.get("description") or "")[:3000]
        description = _with_categories(description, [team, dept])
        results.append(JobResult(
            title=title,
            company=company.name,
            location=cats.get("location", "") or "",
            salary_min=None,
            salary_max=None,
            description=description,
            url=posting.get("hostedUrl") or "",
            source_keyword=keyword,
            created=created,
            job_id=f"lever_{posting.get('id', '')}",
            source_api="careers",
            board_count=total,
        ))
    return results


def _with_categories(description: str, categories: list[str]) -> str:
    """Append team/department labels to the scorer-visible description (not the
    match haystack)."""
    cat_text = " ".join(c for c in categories if c)
    if not cat_text:
        return description
    return (description + " " + cat_text).strip() if description else cat_text


def _matches(keyword: str, title: str) -> bool:
    from scrape.text_match import keyword_matches
    return keyword_matches(keyword, title)
