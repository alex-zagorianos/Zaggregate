from pathlib import Path

import requests

from config import CAREERS_SLOW_TIMEOUT
from models import JobResult
from scrape.cache_helpers import is_failed, mark_failed, read_cache, read_failed, slug_safe, write_cache
from scrape.company_registry import CompanyEntry
from scrape._log import diag
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


def _prime_csrf(tenant: str, n: str, site: str) -> dict:
    """GET the public careers page to harvest the Workday CSRF cookie.
    Returns a dict of extra headers to include on subsequent POSTs.
    Fails silently (returns {}) — CSRF priming is best-effort."""
    careers_url = f"https://{tenant}.wd{n}.myworkdayjobs.com/{site}"
    try:
        resp = requests.get(careers_url, timeout=CAREERS_SLOW_TIMEOUT)
        resp.raise_for_status()
        token = None
        for name in ("CALYPSO_CSRF_TOKEN", "wd-browser-id", "PLAY_SESSION"):
            cookie_jar = getattr(resp, "cookies", {}) or {}
            token = cookie_jar.get(name)
            if token:
                break
        if token:
            return {"X-CALYPSO-CSRF-TOKEN": token}
    except Exception:
        pass
    return {}


def scrape_workday(
    company: CompanyEntry,
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
) -> list[JobResult]:
    parsed = _parse_slug(company.slug)
    if parsed is None:
        diag(f"  [workday] {company.name}: bad slug format '{company.slug}' — expected tenant:N:site")
        return []

    tenant, n, site = parsed
    cache_file = cache_dir / f"workday_{slug_safe(company.slug)}_{slug_safe(keyword)}.json"
    # The results cache above is per-keyword, but a dead tenant fails for every
    # keyword — so the failure marker lives in a company-level file.
    failed_file = cache_dir / f"workday_{slug_safe(company.slug)}_FAILED.json"

    if cache_enabled:
        if is_failed(read_failed(failed_file)):
            return []  # known-dead this FAILED_TTL window (skipped ~a week)
        cached = read_cache(cache_file)
        if cached is not None:
            return _map_results(cached, company, keyword, tenant, n, site)

    url = _WD_BASE.format(tenant=tenant, n=n, site=site)
    # Best-effort CSRF priming (uses requests.get; silently skipped on failure).
    csrf_headers = _prime_csrf(tenant, n, site)

    # Track whether a failure was PERMANENT (404/410 -> dead board, negative-cache
    # for a week) vs TRANSIENT (429 throttle / 5xx outage / network blip -> do NOT
    # poison; today ANY exception poisoned a board for 168h, which the self-
    # inflicted-429 incident showed erodes live coverage).
    saw_permanent = {"v": False}

    def _post(offset: int) -> dict | None:
        payload = {"appliedFacets": {}, "limit": _PAGE_LIMIT, "offset": offset, "searchText": keyword}
        headers = {"Content-Type": "application/json", "Accept": "application/json", **csrf_headers}
        try:
            # Shared session: its urllib3 Retry honors 429 + Retry-After.
            resp = _make_session().post(url, json=payload, headers=headers,
                                        timeout=CAREERS_SLOW_TIMEOUT)
            code = getattr(resp, "status_code", 200)
            if 400 <= code < 500 and code != 429:
                # 404/410/403 etc. -> board removed/renamed: permanent.
                saw_permanent["v"] = True
                diag(f"  [workday] {company.name}: HTTP {code} at offset {offset} — gone")
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            # No status / 429 / 5xx / parse error -> transient. Leave saw_permanent
            # False so the board is retried next run, not marked dead.
            diag(f"  [workday] {company.name}: transient error at offset {offset} — {e}")
            return None

    first = _post(0)
    if first is None:
        # Only negative-cache a genuinely-dead board; a transient failure is
        # retried next run instead of skipped for a week.
        if cache_enabled and saw_permanent["v"]:
            mark_failed(failed_file)
        return []

    postings = list(first.get("jobPostings", []) or [])
    total = first.get("total")
    if isinstance(total, int) and total > len(postings) and len(postings) >= _PAGE_LIMIT:
        # Only page when the first response filled the limit (indicates more pages).
        offset = len(postings)
        pages = 1
        while offset < total and pages < _MAX_PAGES:
            page = _post(offset)
            if not page:
                break
            chunk = page.get("jobPostings", []) or []
            if not chunk or len(chunk) < _PAGE_LIMIT:
                postings.extend(chunk or [])
                break  # short page = last page; stop paging
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
