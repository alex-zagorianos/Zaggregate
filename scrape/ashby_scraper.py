from pathlib import Path
from typing import Optional

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import is_failed, mark_failed, read_cache, slug_safe, write_cache
from scrape.company_registry import CompanyEntry

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
        print(f"  [ashby] {company.name}: HTTP {getattr(e.response, 'status_code', '?')} — skipping")
        if cache_enabled:
            mark_failed(cache_file)
        return []
    except Exception as e:
        print(f"  [ashby] {company.name}: error — {e}")
        if cache_enabled:
            mark_failed(cache_file)
        return []

    if cache_enabled:
        write_cache(cache_file, data)

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

        if not _matches(keyword, title, [dept, team]):
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
            description=(posting.get("descriptionPlain") or "")[:3000],
            url=posting.get("jobUrl") or posting.get("applyUrl") or "",
            source_keyword=keyword,
            created=posting.get("publishedAt") or "",
            job_id=f"ashby_{posting.get('id', '')}",
            source_api="careers",
            board_count=total,
        ))
    return results


def _matches(keyword: str, title: str, categories: list[str]) -> bool:
    from scrape.text_match import keyword_matches
    return keyword_matches(keyword, title + " " + " ".join(c for c in categories if c))
