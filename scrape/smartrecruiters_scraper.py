from pathlib import Path

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import (
    STATUS_PERMANENT, conditional_get, http_cache_body, is_failed, mark_failed,
    read_cache, slug_safe, write_cache,
)
from scrape.company_registry import CompanyEntry
from search.http_util import careers_host_limiter, careers_session, host_of

# SmartRecruiters public postings API — no auth. Mid-market manufacturers
# and industrials skew to SmartRecruiters. Quirk: the postings list has no
# descriptions, so each keyword MATCH costs one extra detail fetch (capped).
_LIST_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
_DETAIL_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}"

# Detail fetches are per-match, uncached postings change rarely; cap to keep
# one slow/huge board from stalling the parallel careers run.
_MAX_DETAIL_FETCHES = 15


def scrape_smartrecruiters(
    company: CompanyEntry,
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
) -> list[JobResult]:
    cache_file = cache_dir / f"smartrecruiters_{slug_safe(company.slug)}.json"
    url = _LIST_URL.format(slug=company.slug)

    if cache_enabled:
        cached = read_cache(cache_file)
        if is_failed(cached):
            return []  # known-dead this TTL window
        if cached is not None:
            return _filter_and_map(http_cache_body(cached), company, keyword,
                                   cache_dir, cache_enabled)

        careers_host_limiter(host_of(url)).acquire()
        result = conditional_get(url, cache_file, timeout=CAREERS_REQUEST_TIMEOUT,
                                 session=careers_session())
        if result.status == STATUS_PERMANENT:
            print(f"  [smartrecruiters] {company.name}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            print(f"  [smartrecruiters] {company.name}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _filter_and_map(result.body, company, keyword, cache_dir, cache_enabled)

    # --no-cache: plain fetch, nothing persisted.
    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [smartrecruiters] {company.name}: error — {e}")
        return []
    return _filter_and_map(data, company, keyword, cache_dir, cache_enabled)


def _fetch_description(company: CompanyEntry, posting_id: str,
                       cache_dir: Path, cache_enabled: bool) -> str:
    """Pull the full job-ad text for one posting (list endpoint omits it).
    Cached per posting; fail-soft to empty string."""
    cache_file = cache_dir / f"smartrecruiters_{slug_safe(company.slug)}_{slug_safe(posting_id)}.json"
    if cache_enabled:
        cached = read_cache(cache_file)
        if cached is not None:
            return _description_from_detail(cached)
    try:
        url = _DETAIL_URL.format(slug=company.slug, posting_id=posting_id)
        careers_host_limiter(host_of(url)).acquire()
        resp = careers_session().get(url, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        detail = resp.json()
    except Exception:
        return ""
    if cache_enabled:
        write_cache(cache_file, detail)
    return _description_from_detail(detail)


def _description_from_detail(detail: dict) -> str:
    import re
    sections = (detail.get("jobAd") or {}).get("sections") or {}
    parts = []
    for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
        text = (sections.get(key) or {}).get("text") or ""
        if text:
            parts.append(text)
    return re.sub(r"<[^>]+>", " ", "\n".join(parts))


def _filter_and_map(data: dict, company: CompanyEntry, keyword: str,
                    cache_dir: Path, cache_enabled: bool) -> list[JobResult]:
    postings = data.get("content", [])
    # totalFound covers the whole board even when paginated past limit=100.
    total = data.get("totalFound") or len(postings)
    results = []
    detail_fetches = 0
    for posting in postings:
        title = posting.get("name", "") or ""
        function = ((posting.get("function") or {}).get("label")) or ""
        department = ((posting.get("department") or {}).get("label")) or ""

        # Match on the TITLE only; function/department reach the scorer via the
        # description path below, never the keyword haystack.
        if not _matches(keyword, title):
            continue

        posting_id = posting.get("id", "")
        description = ""
        if posting_id and detail_fetches < _MAX_DETAIL_FETCHES:
            description = _fetch_description(company, posting_id, cache_dir, cache_enabled)
            detail_fetches += 1
        # Slice the ad text first, then append category labels so they survive
        # the 3000-char cap and stay visible to the scorer.
        description = _with_categories(description[:3000], [function, department])

        loc = posting.get("location") or {}
        location = ", ".join(p for p in (loc.get("city"), loc.get("region"),
                                         loc.get("country")) if p)
        if loc.get("remote"):
            location = f"Remote{' / ' + location if location else ''}"

        ref = posting.get("ref") or ""  # API detail URL, not human-facing
        results.append(JobResult(
            title=title,
            company=company.name,
            location=location,
            salary_min=None,  # not exposed by the public API; scorer recovers
            salary_max=None,  # ranges from the description text
            description=description,
            url=f"https://jobs.smartrecruiters.com/{company.slug}/{posting_id}" if posting_id else ref,
            source_keyword=keyword,
            created=posting.get("releasedDate") or "",
            job_id=f"smartrecruiters_{posting_id}",
            source_api="careers",
            board_count=int(total),
        ))
    return results


def _with_categories(description: str, categories: list[str]) -> str:
    """Append function/department labels to the scorer-visible description (not
    the match haystack)."""
    cat_text = " ".join(c for c in categories if c)
    if not cat_text:
        return description
    return (description + " " + cat_text).strip() if description else cat_text


def _matches(keyword: str, title: str) -> bool:
    from scrape.text_match import keyword_matches
    return keyword_matches(keyword, title)
