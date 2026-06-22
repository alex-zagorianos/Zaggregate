from pathlib import Path
from urllib.parse import urljoin
import hashlib

import requests
from bs4 import BeautifulSoup

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import is_failed, mark_failed, read_cache, write_cache
from scrape.company_registry import CompanyEntry

_JOB_URL_PATTERNS = ("/job/", "/jobs/", "/opening/", "/openings/", "/position/", "/careers/job", "/career/")
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def scrape_direct(
    company: CompanyEntry,
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
) -> list[JobResult]:
    url_hash = hashlib.md5(company.slug.encode()).hexdigest()[:12]
    cache_file = cache_dir / f"direct_{url_hash}.html"
    # Negative-cache marker: a dead URL (404/403/timeout) was retried once per
    # keyword per run — ~150 doomed 20s requests a day across the registry's
    # dead entries. The shared is_failed/mark_failed JSON marker (used by
    # gh/lever/ashby/smartrecruiters) makes it one attempt per TTL window.
    failed_file = cache_dir / f"direct_{url_hash}_FAILED.json"

    if cache_enabled:
        if is_failed(read_cache(failed_file)):
            return []  # known-dead this TTL window; stay quiet, don't re-fetch
        html = read_cache(cache_file)
    else:
        html = None

    if html is None:
        try:
            resp = requests.get(
                company.slug, headers=_HEADERS, timeout=CAREERS_REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            print(f"  [direct] {company.name}: fetch error — {e}")
            if cache_enabled:
                mark_failed(failed_file)
            return []
        if cache_enabled:
            write_cache(cache_file, html)

    print(f"  [direct] {company.name}: basic link extraction only — verify results manually")
    return _extract_jobs(html, company, keyword)


def _extract_jobs(html: str, company: CompanyEntry, keyword: str) -> list[JobResult]:
    soup = BeautifulSoup(html, "html.parser")
    base = company.slug
    results = []
    seen_urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if not text or not _is_job_link(href):
            continue
        if not _matches(keyword, text):
            continue
        full_url = urljoin(base, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        results.append(JobResult(
            title=text[:200],
            company=company.name,
            location="",
            salary_min=None,
            salary_max=None,
            description="",
            url=full_url,
            source_keyword=keyword,
            created="",
            job_id=f"direct_{hashlib.md5(full_url.encode()).hexdigest()[:8]}",
            source_api="careers",
        ))

    return results


def _is_job_link(href: str) -> bool:
    href_lower = href.lower()
    return any(pat in href_lower for pat in _JOB_URL_PATTERNS)


def _matches(keyword: str, text: str) -> bool:
    from scrape.text_match import keyword_matches
    return keyword_matches(keyword, text)
