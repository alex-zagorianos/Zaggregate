from pathlib import Path
from typing import Optional

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import (
    STATUS_PERMANENT, conditional_get, http_cache_body, is_failed, mark_failed,
    read_cache, slug_safe,
)
from scrape.company_registry import CompanyEntry
from search.http_util import careers_host_limiter, careers_session, host_of

# Ashby public job-posting API — no auth. The newest/smallest startups skew
# heavily to Ashby (e.g. Gecko Robotics), so this unlocks exactly the
# small-company segment Greenhouse/Lever miss.
_BASE_URL = ("https://api.ashbyhq.com/posting-api/job-board/{slug}"
             "?includeCompensation=true")


def scrape_ashby(
    company: CompanyEntry,
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
) -> list[JobResult]:
    cache_file = cache_dir / f"ashby_{slug_safe(company.slug)}.json"
    url = _BASE_URL.format(slug=company.slug)

    if cache_enabled:
        cached = read_cache(cache_file)
        if is_failed(cached):
            return []  # known-dead this TTL window
        if cached is not None:
            return _filter_and_map(http_cache_body(cached), company, keyword)

        # TTL-stale/first-ever: conditional GET (429/5xx serves stale + never
        # poisons; 404/410 marks dead), rate-limited + Retry-After honored.
        careers_host_limiter(host_of(url)).acquire()
        result = conditional_get(url, cache_file, timeout=CAREERS_REQUEST_TIMEOUT,
                                 session=careers_session())
        if result.status == STATUS_PERMANENT:
            print(f"  [ashby] {company.name}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            print(f"  [ashby] {company.name}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _filter_and_map(result.body, company, keyword)

    # cache_enabled is False (CLI --no-cache): plain fetch, nothing persisted.
    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [ashby] {company.name}: error — {e}")
        return []
    return _filter_and_map(data, company, keyword)


def _salary_range(posting: dict) -> tuple[Optional[float], Optional[float]]:
    """Best-effort min/max from Ashby's nested compensation object; the
    structure varies, so fail soft — the scorer also parses pay ranges out of
    the description text."""
    comp = posting.get("compensation") or {}
    try:
        for tier in comp.get("compensationTiers") or []:
            for c in tier.get("components") or []:
                if (c.get("compensationType") or "").lower() == "salary":
                    lo, hi = c.get("minValue"), c.get("maxValue")
                    if lo or hi:
                        return (float(lo) if lo else None,
                                float(hi) if hi else None)
        for c in comp.get("summaryComponents") or []:
            if (c.get("compensationType") or "").lower() == "salary":
                lo, hi = c.get("minValue"), c.get("maxValue")
                if lo or hi:
                    return (float(lo) if lo else None,
                            float(hi) if hi else None)
    except (TypeError, ValueError, AttributeError):
        pass
    return (None, None)


def _filter_and_map(data: dict, company: CompanyEntry, keyword: str) -> list[JobResult]:
    postings = [p for p in data.get("jobs", []) if p.get("isListed", True)]
    total = len(postings)  # company-size proxy: whole board is in hand
    results = []
    for posting in postings:
        title = posting.get("title", "") or ""
        dept = posting.get("department", "") or ""
        team = posting.get("team", "") or ""

        # Match on the TITLE only; department/team reach the scorer via the
        # description path below, never the keyword haystack.
        if not _matches(keyword, title):
            continue

        location = posting.get("location", "") or ""
        secondary = [
            (s.get("location") or "") for s in posting.get("secondaryLocations") or []
        ]
        if secondary:
            location = "; ".join([location, *[s for s in secondary if s]])

        salary_min, salary_max = _salary_range(posting)
        results.append(JobResult(
            title=title,
            company=company.name,
            location=location,
            salary_min=salary_min,
            salary_max=salary_max,
            description=_with_categories(
                (posting.get("descriptionPlain") or "")[:3000], [dept, team]),
            url=posting.get("jobUrl") or posting.get("applyUrl") or "",
            source_keyword=keyword,
            created=posting.get("publishedAt") or "",
            job_id=f"ashby_{posting.get('id', '')}",
            source_api="careers",
            board_count=total,
        ))
    return results


def _with_categories(description: str, categories: list[str]) -> str:
    """Append department/team labels to the scorer-visible description (not the
    match haystack)."""
    cat_text = " ".join(c for c in categories if c)
    if not cat_text:
        return description
    return (description + " " + cat_text).strip() if description else cat_text


def _matches(keyword: str, title: str) -> bool:
    from scrape.text_match import keyword_matches
    return keyword_matches(keyword, title)
