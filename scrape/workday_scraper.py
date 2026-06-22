from pathlib import Path

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import is_failed, mark_failed, read_cache, slug_safe, write_cache
from scrape.company_registry import CompanyEntry
from search.http_util import make_session as _make_session

# Workday exposes a consistent undocumented JSON endpoint across all tenants.
# Slug format stored in CompanyEntry.slug: "tenant:N:site"
#   e.g. "cat:5:CaterpillarCareers"
#   → POST https://cat.wd5.myworkdayjobs.com/wday/cxs/cat/CaterpillarCareers/jobs
_WD_BASE = "https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"

_PAGE_LIMIT = 20          # Workday CXS hard per-response cap
_MAX_PAGES = 50           # offset paging ceiling (1000 postings) to bound a run


def _job_url(tenant: str, n: str, site: str, external_path: str) -> str:
    """Build the public posting URL from a CXS externalPath.

    The CXS jobs endpoint returns externalPath site-relative ("/job/Loc/Title_R1")
    with no site segment, so host+externalPath 404s. The browser-facing URL needs
    the site inserted: ".../CaterpillarCareers/job/...". Some tenants already embed
    the site (or a locale + site) in externalPath, so only insert when it's absent.
    """
    if not external_path:
        return ""
    host = f"https://{tenant}.wd{n}.myworkdayjobs.com"
    if f"/{site}/" in external_path:
        return host + external_path  # site (and any locale) already present
    return f"{host}/{site}{external_path}"


def _parse_slug(slug: str) -> tuple[str, str, str] | None:
    """Parse 'tenant:N:site' → (tenant, n, site). Returns None if malformed."""
    parts = slug.split(":", 2)
    if len(parts) != 3:
        return None
    tenant, n, site = parts
    if not tenant or not n.isdigit() or not site:
        return None
    return tenant, n, site


def _prime_session(tenant: str, n: str, site: str):
    """GET the public careers page so Workday sets its CSRF cookie/token on the
    session; mirror the token into a header. Returns a primed session, or a
    fresh un-primed one if the GET fails (caller falls back to a bare POST)."""
    session = _make_session()
    session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    careers_url = f"https://{tenant}.wd{n}.myworkdayjobs.com/{site}"
    try:
        resp = session.get(careers_url, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        token = None
        for name in ("CALYPSO_CSRF_TOKEN", "wd-browser-id", "PLAY_SESSION"):
            token = (getattr(resp, "cookies", {}) or {}).get(name) or session.cookies.get(name)
            if token:
                break
        if token:
            session.headers["X-CALYPSO-CSRF-TOKEN"] = token
    except Exception:
        pass
    return session


def scrape_workday(
    company: CompanyEntry,
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
) -> list[JobResult]:
    parsed = _parse_slug(company.slug)
    if parsed is None:
        print(f"  [workday] {company.name}: bad slug format '{company.slug}' — expected tenant:N:site")
        return []

    tenant, n, site = parsed
    cache_file = cache_dir / f"workday_{slug_safe(company.slug)}_{slug_safe(keyword)}.json"
    # The results cache above is per-keyword, but a dead tenant fails for every
    # keyword — so the failure marker lives in a company-level file.
    failed_file = cache_dir / f"workday_{slug_safe(company.slug)}_FAILED.json"

    if cache_enabled:
        if is_failed(read_cache(failed_file)):
            return []  # known-dead this TTL window
        cached = read_cache(cache_file)
        if cached is not None:
            return _map_results(cached, company, keyword, tenant, n, site)

    url = _WD_BASE.format(tenant=tenant, n=n, site=site)
    session = _prime_session(tenant, n, site)

    def _post(offset: int) -> dict | None:
        payload = {"appliedFacets": {}, "limit": _PAGE_LIMIT, "offset": offset, "searchText": keyword}
        try:
            resp = session.post(url, json=payload, timeout=CAREERS_REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  [workday] {company.name}: HTTP error at offset {offset} — {e}")
            return None

    first = _post(0)
    if first is None:
        if cache_enabled:
            mark_failed(failed_file)
        return []

    postings = list(first.get("jobPostings", []) or [])
    total = first.get("total")
    if isinstance(total, int) and total > len(postings):
        offset = len(postings)
        pages = 1
        while offset < total and pages < _MAX_PAGES:
            page = _post(offset)
            if not page:
                break
            chunk = page.get("jobPostings", []) or []
            if not chunk:
                break
            postings.extend(chunk)
            offset += _PAGE_LIMIT
            pages += 1
    data = {"total": total, "jobPostings": postings}

    if cache_enabled:
        write_cache(cache_file, data)

    return _map_results(data, company, keyword, tenant, n, site)


def _map_results(
    data: dict,
    company: CompanyEntry,
    keyword: str,
    tenant: str,
    n: str,
    site: str,
) -> list[JobResult]:
    results = []
    # Workday's CXS jobs response exposes the whole-board total here; feed it to
    # the scorer's company-size proxy (was omitted -> -1 -> no size adjustment,
    # so mega boards like Caterpillar never got the -6 nudge).
    total = data.get("total")
    board_count = int(total) if isinstance(total, int) else -1
    for job in data.get("jobPostings", []):
        title = job.get("title", "") or ""
        if not title:
            continue

        location = job.get("locationsText", "") or ""
        external_path = job.get("externalPath", "") or ""
        job_url = _job_url(tenant, n, site, external_path)

        req_id = job.get("reqId", "") or ""
        job_id = f"workday_{slug_safe(tenant)}_{req_id}" if req_id else f"workday_{slug_safe(title)}"

        results.append(JobResult(
            title=title,
            company=company.name,
            location=location,
            salary_min=None,
            salary_max=None,
            description="",
            url=job_url,
            source_keyword=keyword,
            created="",
            job_id=job_id,
            source_api="careers",
            board_count=board_count,
        ))
    return results
