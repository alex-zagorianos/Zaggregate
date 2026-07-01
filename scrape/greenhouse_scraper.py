import html
import re
from pathlib import Path
from typing import Optional

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import (
    STATUS_PERMANENT, conditional_get, http_cache_body, is_failed, mark_failed,
    read_cache, slug_safe,
)
from scrape.company_registry import CompanyEntry
from scrape.greenhouse_url import embed_url
from search.http_util import careers_host_limiter, careers_session, host_of

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
        # costs a cheap 304 instead of a full re-download. Routed through the
        # shared retry/Retry-After session + a per-host rate limiter so a burst
        # of greenhouse boards can't self-inflict a 429.
        careers_host_limiter(host_of(url)).acquire()
        result = conditional_get(url, cache_file, timeout=CAREERS_REQUEST_TIMEOUT,
                                 session=careers_session())
        if result.status == STATUS_PERMANENT:
            # Genuinely dead (404/410) — negative-cache it, exactly as before.
            print(f"  [greenhouse] {company.name}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            # Transient (429/5xx/network) with no stale snapshot — skip WITHOUT
            # poisoning; the board is retried next run.
            print(f"  [greenhouse] {company.name}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _filter_and_map(result.body, company, keyword)

    try:
        resp = requests.get(url, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        print(f"  [greenhouse] {company.name}: HTTP {getattr(e.response, 'status_code', '?')} — skipping")
        return []
    except Exception as e:
        print(f"  [greenhouse] {company.name}: error — {e}")
        return []

    return _filter_and_map(data, company, keyword)


def _filter_and_map(data: dict, company: CompanyEntry, keyword: str) -> list[JobResult]:
    # Total board size is free here and is a decent company-size proxy.
    total = (data.get("meta") or {}).get("total") or len(data.get("jobs", []))
    results = []
    for job in data.get("jobs", []):
        title = job.get("title", "") or ""
        depts = [d.get("name", "") for d in job.get("departments", [])]
        # Match on the TITLE only — a "controls engineer" query must not be
        # satisfied by an "Engineering" department label on an off-target role.
        # Department text still reaches the scorer via the description path below.
        if not _matches(keyword, title):
            continue

        location = (job.get("location") or {}).get("name") or ""
        # Greenhouse's absolute_url is often the company's own JS careers SPA,
        # which can render a generic "Work at X" page instead of the job. Build
        # the server-rendered hosted application URL from slug + id instead;
        # fall back to absolute_url only if the id is missing.
        gh_id = job.get("id")
        job_url = embed_url(company.slug, gh_id) if gh_id else (job.get("absolute_url") or "")
        results.append(JobResult(
            title=title,
            company=company.name,
            location=location,
            salary_min=None,
            salary_max=None,
            description=_with_departments(_clean_content(job.get("content", "")), depts),
            url=job_url,
            source_keyword=keyword,
            # first_published is the real posting date; updated_at makes big
            # boards that touch postings look perpetually fresh.
            created=job.get("first_published") or job.get("updated_at") or "",
            job_id=f"greenhouse_{job.get('id', '')}",
            source_api="careers",
            board_count=total,
        ))
    return results


def _with_departments(description: str, departments: list[str]) -> str:
    """Fold department/team labels into the scorer-visible description (not the
    match haystack) so they contribute to skill overlap without letting a dept
    label alone satisfy a title keyword query."""
    dept_text = " ".join(d for d in departments if d)
    if not dept_text:
        return description
    return (description + " " + dept_text).strip() if description else dept_text


def _matches(keyword: str, title: str) -> bool:
    from scrape.text_match import keyword_matches
    return keyword_matches(keyword, title)
