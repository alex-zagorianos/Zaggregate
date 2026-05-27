from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import read_cache, slug_safe, write_cache
from scrape.company_registry import CompanyEntry

_BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def scrape_greenhouse(
    company: CompanyEntry,
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
) -> list[JobResult]:
    cache_file = cache_dir / f"greenhouse_{slug_safe(company.slug)}.json"

    if cache_enabled:
        cached = read_cache(cache_file)
        if cached is not None:
            return _filter_and_map(cached, company, keyword)

    try:
        url = _BASE_URL.format(slug=company.slug)
        resp = requests.get(url, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        print(f"  [greenhouse] {company.name}: HTTP {e.response.status_code} — skipping")
        return []
    except Exception as e:
        print(f"  [greenhouse] {company.name}: error — {e}")
        return []

    if cache_enabled:
        write_cache(cache_file, data)

    return _filter_and_map(data, company, keyword)


def _filter_and_map(data: dict, company: CompanyEntry, keyword: str) -> list[JobResult]:
    results = []
    for job in data.get("jobs", []):
        title = job.get("title", "") or ""
        depts = [d.get("name", "") for d in job.get("departments", [])]
        if not _matches(keyword, title, depts):
            continue

        location = job.get("location", {}).get("name") or ""
        results.append(JobResult(
            title=title,
            company=company.name,
            location=location,
            salary_min=None,
            salary_max=None,
            description="",
            url=job.get("absolute_url") or "",
            source_keyword=keyword,
            created=job.get("updated_at") or "",
            job_id=f"greenhouse_{job.get('id', '')}",
            source_api="careers",
        ))
    return results


def _matches(keyword: str, title: str, departments: list[str]) -> bool:
    kw = keyword.lower()
    haystack = title.lower() + " " + " ".join(d.lower() for d in departments)
    if kw in haystack:
        return True
    return any(part in haystack for part in kw.split() if len(part) >= 4)
