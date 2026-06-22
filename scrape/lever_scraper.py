from datetime import datetime, timezone
from pathlib import Path

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import is_failed, mark_failed, read_cache, slug_safe, write_cache
from scrape.company_registry import CompanyEntry

_BASE_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"


def scrape_lever(
    company: CompanyEntry,
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
) -> list[JobResult]:
    cache_file = cache_dir / f"lever_{slug_safe(company.slug)}.json"

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
        data = resp.json()  # returns a list, not a dict
    except requests.HTTPError as e:
        print(f"  [lever] {company.name}: HTTP {getattr(e.response, 'status_code', '?')} — skipping")
        if cache_enabled:
            mark_failed(cache_file)
        return []
    except Exception as e:
        print(f"  [lever] {company.name}: error — {e}")
        if cache_enabled:
            mark_failed(cache_file)
        return []

    if cache_enabled:
        write_cache(cache_file, data)

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
