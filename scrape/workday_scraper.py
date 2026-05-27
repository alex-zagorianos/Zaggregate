from datetime import datetime
from pathlib import Path

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import read_cache, slug_safe, write_cache
from scrape.company_registry import CompanyEntry

# Workday exposes a consistent undocumented JSON endpoint across all tenants.
# Slug format stored in CompanyEntry.slug: "tenant:N:site"
#   e.g. "cat:5:CaterpillarCareers"
#   → POST https://cat.wd5.myworkdayjobs.com/wday/cxs/cat/CaterpillarCareers/jobs
_WD_BASE = "https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
_WD_JOB_URL = "https://{tenant}.wd{n}.myworkdayjobs.com{path}"


def _parse_slug(slug: str) -> tuple[str, str, str] | None:
    """Parse 'tenant:N:site' → (tenant, n, site). Returns None if malformed."""
    parts = slug.split(":", 2)
    if len(parts) != 3:
        return None
    tenant, n, site = parts
    if not tenant or not n.isdigit() or not site:
        return None
    return tenant, n, site


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

    if cache_enabled:
        cached = read_cache(cache_file)
        if cached is not None:
            return _map_results(cached, company, keyword, tenant, n)

    url = _WD_BASE.format(tenant=tenant, n=n, site=site)
    payload = {
        "appliedFacets": {},
        "limit": 20,
        "offset": 0,
        "searchText": keyword,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        print(f"  [workday] {company.name}: HTTP {e.response.status_code} — check tenant/site slug")
        return []
    except Exception as e:
        print(f"  [workday] {company.name}: error — {e}")
        return []

    if cache_enabled:
        write_cache(cache_file, data)

    return _map_results(data, company, keyword, tenant, n)


def _map_results(
    data: dict,
    company: CompanyEntry,
    keyword: str,
    tenant: str,
    n: str,
) -> list[JobResult]:
    results = []
    for job in data.get("jobPostings", []):
        title = job.get("title", "") or ""
        if not title:
            continue

        location = job.get("locationsText", "") or ""
        external_path = job.get("externalPath", "") or ""
        job_url = _WD_JOB_URL.format(tenant=tenant, n=n, path=external_path) if external_path else ""

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
        ))
    return results
