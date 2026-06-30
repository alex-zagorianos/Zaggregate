from pathlib import Path
from urllib.parse import urljoin
import hashlib

import requests
from bs4 import BeautifulSoup

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import is_failed, mark_failed, read_cache, read_failed, write_cache
from scrape.company_registry import CompanyEntry
from scrape.jsonld_scraper import extract_jobs as _jsonld_extract

_JOB_URL_PATTERNS = ("/job/", "/jobs/", "/opening/", "/openings/", "/position/", "/careers/job", "/career/")
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _looks_js_shell(html: str) -> bool:
    """True when the HTML looks like a JS-gated SPA shell: very short or
    contains no anchor elements that a browser would render. Used to decide
    whether to escalate to the Scrapling fallback on an apparent 200 response."""
    stripped = html.strip()
    if len(stripped) < 2000:
        return True
    # No <a  links -> nothing for link-extraction to find; probably client-rendered.
    if "<a " not in stripped.lower():
        return True
    return False


def _fetch_html(company: CompanyEntry, cache_dir: Path, cache_enabled: bool) -> str | None:
    """Fetch (or read cached) HTML for a company's page, with the shared
    negative-failure cache. Returns None on a known-dead or failed fetch.
    Factored out so the JSON-LD scraper can reuse the same fetch + cache path.

    When a plain requests fetch fails (403/anti-bot/timeout) or returns a
    JS-only shell, the Scrapling stealth fetcher is tried as a fallback if
    config.SCRAPLING_FALLBACK is true and the scrapling package is installed.
    The fallback is lazy-imported so normal runs never touch scrapling."""
    url_hash = hashlib.md5(company.slug.encode()).hexdigest()[:12]
    cache_file = cache_dir / f"direct_{url_hash}.html"
    # Negative-cache marker: a dead URL (404/403/timeout) was retried once per
    # keyword per run — ~150 doomed requests a day across the registry's dead
    # entries. The shared is_failed/mark_failed JSON marker (used by
    # gh/lever/ashby/smartrecruiters) makes it one attempt per TTL window;
    # read_failed gives that marker the long FAILED_TTL so a dead URL is skipped
    # for ~a week instead of being re-probed (at full timeout) every daily run.
    failed_file = cache_dir / f"direct_{url_hash}_FAILED.json"

    if cache_enabled:
        if is_failed(read_failed(failed_file)):
            return None  # known-dead this FAILED_TTL window; don't re-fetch
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
            print(f"  [direct] {company.name}: fetch error -- {e}")
            # (a) Try stealth fallback before marking the URL as dead.
            import config
            from scrape import stealth_fetch
            if config.SCRAPLING_FALLBACK and stealth_fetch.available():
                print(f"  [direct] {company.name}: escalating to stealth fetch")
                html = stealth_fetch.fetch_html(company.slug)
                if html:
                    if cache_enabled:
                        write_cache(cache_file, html)
                    return html
            # Both requests and stealth fallback failed.
            if cache_enabled:
                mark_failed(failed_file)
            return None

        # (b) 200 response but JS-only shell -- try stealth fetch for rendered HTML.
        if _looks_js_shell(html):
            import config
            from scrape import stealth_fetch
            if config.SCRAPLING_FALLBACK and stealth_fetch.available():
                print(f"  [direct] {company.name}: JS shell detected, escalating to stealth fetch")
                fallback = stealth_fetch.fetch_html(company.slug)
                if fallback:
                    html = fallback

        if cache_enabled:
            write_cache(cache_file, html)
    return html


def scrape_direct(
    company: CompanyEntry,
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
) -> list[JobResult]:
    html = _fetch_html(company, cache_dir, cache_enabled)
    if html is None:
        return []

    print(f"  [direct] {company.name}: link extraction + JSON-LD — verify results manually")
    jobs = _extract_jobs(html, company, keyword)
    return _merge_jsonld(jobs, html, company, keyword)


def _merge_jsonld(jobs: list[JobResult], html: str, company: CompanyEntry,
                  keyword: str) -> list[JobResult]:
    """Additively fold any schema.org/JobPosting JSON-LD on the SAME page into the
    link-extracted results — strictly more, never fewer (deduped by identity_key).
    A direct page that embeds structured JobPosting data (common on modern career
    sites) now yields those richer postings too, instead of link text only."""
    existing = {j.identity_key for j in jobs}
    for j in _jsonld_extract(html, company.slug, keyword=keyword):
        if not j.company:
            j.company = company.name
        if j.identity_key not in existing:
            existing.add(j.identity_key)
            jobs.append(j)
    return jobs


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
