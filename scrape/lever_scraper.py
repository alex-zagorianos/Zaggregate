from datetime import datetime, timezone
from pathlib import Path

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import read_cache, slug_safe, write_cache
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
        if cached is not None:
            return _filter_and_map(cached, company, keyword)

    try:
        url = _BASE_URL.format(slug=company.slug)
        resp = requests.get(url, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()  # returns a list, not a dict
    except requests.HTTPError as e:
        print(f"  [lever] {company.name}: HTTP {e.response.status_code} — skipping")
        return []
    except Exception as e:
        print(f"  [lever] {company.name}: error — {e}")
        return []

    if cache_enabled:
        write_cache(cache_file, data)

    return _filter_and_map(data, company, keyword)


def _filter_and_map(postings: list, company: CompanyEntry, keyword: str) -> list[JobResult]:
    results = []
    for posting in postings:
        title = posting.get("text", "") or ""
        cats = posting.get("categories", {}) or {}
        team = cats.get("team", "") or ""
        dept = cats.get("department", "") or ""

        if not _matches(keyword, title, [team, dept]):
            continue

        created_ms = posting.get("createdAt")
        if created_ms:
            created = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        else:
            created = ""

        results.append(JobResult(
            title=title,
            company=company.name,
            location=cats.get("location", "") or "",
            salary_min=None,
            salary_max=None,
            description="",
            url=posting.get("hostedUrl") or "",
            source_keyword=keyword,
            created=created,
            job_id=f"lever_{posting.get('id', '')}",
            source_api="careers",
        ))
    return results


def _matches(keyword: str, title: str, categories: list[str]) -> bool:
    kw = keyword.lower()
    haystack = title.lower() + " " + " ".join(c.lower() for c in categories if c)
    if kw in haystack:
        return True
    return any(part in haystack for part in kw.split() if len(part) >= 4)
