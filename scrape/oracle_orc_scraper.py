"""Oracle Recruiting Cloud (ORC / Fusion HCM CandidateExperience) scraper.

ToS-gray, mirrors workday_scraper's polite handling: this is the same public
career-site XHR a browser fires un-authenticated to render an Oracle-hosted
careers page. Big non-tech employers (hospitals, universities, Fortune-1000)
live here -- e.g. UC Health, TriHealth (both Cincinnati, both validated live
2026-07-01).

Endpoint:
    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
        ?onlyData=true
        &expand=requisitionList.secondaryLocations
        &finder=findReqs;siteNumber={CX_...},keyword={kw},limit={N},offset={M}
      headers: ora-irc-cx-userid: {any-uuid}, ora-irc-language: en
      -> {"items": [ {"TotalJobsCount": T, "requisitionList": [ {req}, ... ] } ],
          "count": ..., "hasMore": ...}

`host` is the Oracle Fusion tenant host (e.g. eswt.fa.us6.oraclecloud.com).
`siteNumber` ("CX_1", "CX_1001", ...) identifies the CandidateExperience site
and is REQUIRED. It is normally scraped ONCE from the tenant's
CandidateExperience page URL/HTML and cached in CompanyEntry.extra["site"];
discover_site_number() implements that one-time discovery.

CompanyEntry.slug = the host; CompanyEntry.extra = {"site": "CX_1"}.

Requisition shape (validated live): each requisition in requisitionList carries
`Title`, `Id`, `PrimaryLocation`, `PostedDate`, `secondaryLocations`,
`ShortDescriptionStr`. items[0].TotalJobsCount is the whole-board total.

Routed through careers_session + per-host limiter; paged to a bounded ceiling;
fail-soft -> []. A dead host is negative-cached for the FAILED TTL window.
"""
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from config import CACHE_DIR, CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import slug_safe, is_failed, mark_failed, read_cache, write_cache
from scrape.html_text import strip_html_to_text
from search.http_util import careers_host_limiter, careers_session, host_of

_PATH = "/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
_JOB_URL = "https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{id}"
_PAGE = 50               # ORC returns up to ~25-50 per page; request 50
_MAX_PAGES = 40          # ceiling (2000 reqs) to bound a run
# A stable-but-anonymous browser id header the CX SPA sends. Any UUID works.
_CX_USERID = "00000000-0000-0000-0000-000000000000"
_SITE_RE = re.compile(r"CX_\d{1,6}")

try:
    from config import FAILED_TTL_HOURS as _FAILED_TTL
except Exception:
    _FAILED_TTL = 168


def _headers() -> dict:
    return {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JobSearchTool/1.0",
        "ora-irc-cx-userid": _CX_USERID,
        "ora-irc-language": "en",
    }


def discover_site_number(host: str, *, session=None) -> str:
    """One-time siteNumber discovery from a tenant's CandidateExperience page.

    Fetches the CX requisitions page and extracts the CX_N site code from the
    URL/HTML. Returns "" on any failure (caller then can't scrape -> fail-soft).
    Used at onboarding/probe time and cached into CompanyEntry.extra["site"], so
    a real daily run never pays this request. Polite: single GET through the
    shared limiter + session.
    """
    host = (host or "").strip()
    if not host:
        return ""
    page = f"https://{host}/hcmUI/CandidateExperience/en/sites/CX_1/requisitions"
    sess = session or careers_session()
    careers_host_limiter(host).acquire()
    try:
        resp = sess.get(page, headers={"User-Agent": _headers()["User-Agent"]},
                        timeout=CAREERS_REQUEST_TIMEOUT, allow_redirects=True)
        # The effective URL (after any redirect) usually carries the real site.
        final = getattr(resp, "url", "") or ""
        m = _SITE_RE.search(final)
        if m:
            return m.group(0)
        text = getattr(resp, "text", "") or ""
        m = _SITE_RE.search(text)
        if m:
            return m.group(0)
    except Exception:
        return ""
    return ""


def _site_of(company_or_slug, extra: Optional[dict]) -> str:
    site = ""
    if isinstance(extra, dict):
        site = (extra.get("site") or "").strip()
    return site


def fetch(slug: str, *, keyword: str = "", site: str = "",
          cache_dir: Optional[Path] = None, cache_enabled: bool = False,
          company_name: str = "") -> list[JobResult]:
    host = (slug or "").strip().lower()
    if not host:
        return []
    site = (site or "").strip()
    if not site:
        # No cached siteNumber -> discover once (this is the fallback path; the
        # dispatcher passes the cached extra["site"] so a normal run skips this).
        site = discover_site_number(host)
        if not site:
            print(f"  [oracle_orc] {host}: no siteNumber (CX_N) discoverable — skipping")
            return []

    cache_file = ((cache_dir or CACHE_DIR) / f"oracleorc_{slug_safe(host)}_{slug_safe(site)}.json"
                  if cache_enabled else None)
    failed_file = ((cache_dir or CACHE_DIR) / f"oracleorc_{slug_safe(host)}_{slug_safe(site)}_FAILED.json"
                   if cache_enabled else None)

    if cache_enabled and failed_file is not None:
        if is_failed(read_cache(failed_file, ttl_hours=_FAILED_TTL)):
            return []
        cached = read_cache(cache_file)
        if cached is not None:
            return _map(cached, host, site, keyword, company_name)

    # Fetch the FULL board (no server-side keyword) so one cached snapshot serves
    # every keyword in a run; keyword filtering is applied locally in _map. This
    # mirrors how greenhouse/workday cache the whole board rather than a filtered
    # slice.
    reqs, total, permanent = _fetch_all(host, site, "")
    if reqs is None:
        if cache_enabled and permanent and failed_file is not None:
            mark_failed(failed_file)
        return []
    data = {"total": total, "requisitionList": reqs}
    if cache_enabled and cache_file is not None:
        write_cache(cache_file, data)
    return _map(data, host, site, keyword, company_name)


def _finder(site: str, keyword: str, limit: int, offset: int) -> str:
    parts = [f"findReqs;siteNumber={site}"]
    if keyword:
        parts.append(f"keyword={quote(keyword)}")
    parts.append(f"limit={limit}")
    parts.append(f"offset={offset}")
    return ",".join(parts)


def _fetch_all(host: str, site: str, keyword: str):
    """Page the requisitions. Returns (reqs|None, total, saw_permanent)."""
    base = f"https://{host}{_PATH}"
    all_reqs: list[dict] = []
    total = -1
    saw_permanent = False
    for page in range(_MAX_PAGES):
        offset = page * _PAGE
        params = {
            "onlyData": "true",
            "expand": "requisitionList.secondaryLocations",
            "finder": _finder(site, keyword, _PAGE, offset),
        }
        careers_host_limiter(host).acquire()
        try:
            resp = careers_session().get(base, params=params, headers=_headers(),
                                         timeout=CAREERS_REQUEST_TIMEOUT)
            code = getattr(resp, "status_code", 200)
            if 400 <= code < 500 and code != 429:
                saw_permanent = True
                if page == 0:
                    print(f"  [oracle_orc] {host}/{site}: HTTP {code} — gone, skipping")
                    return None, total, True
                break
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            if page == 0:
                print(f"  [oracle_orc] {host}/{site}: transient error — {e}")
                return None, total, False
            break
        items = body.get("items") if isinstance(body, dict) else None
        if not items:
            break
        item0 = items[0] if isinstance(items, list) and items else {}
        if isinstance(item0, dict) and isinstance(item0.get("TotalJobsCount"), int):
            total = item0["TotalJobsCount"]
        chunk = (item0.get("requisitionList") or []) if isinstance(item0, dict) else []
        if not chunk:
            break
        all_reqs.extend(chunk)
        if len(chunk) < _PAGE:
            break
        if total >= 0 and len(all_reqs) >= total:
            break
    if not all_reqs and total < 0:
        return [], 0, saw_permanent
    return all_reqs, (total if total >= 0 else len(all_reqs)), saw_permanent


def _clean(raw: str) -> str:
    return strip_html_to_text(raw)


def _location(req: dict) -> str:
    loc = (req.get("PrimaryLocation") or "").strip()
    if loc:
        return loc
    secs = req.get("secondaryLocations") or []
    if isinstance(secs, list) and secs and isinstance(secs[0], dict):
        return (secs[0].get("Name") or secs[0].get("PrimaryLocation") or "").strip()
    return ""


def _map(data: dict, host: str, site: str, keyword: str,
         company_name: str = "") -> list[JobResult]:
    reqs = data.get("requisitionList") or []
    total = data.get("total")
    board_count = int(total) if isinstance(total, int) and total >= 0 else len(reqs)
    # Registry display name first: the tenant host is an opaque Oracle id
    # ("fa-evly-saasfaprod1" -> "Fa Evly Saasfaprod1"), not the employer.
    company = (company_name or "").strip() or host.split(".")[0].replace("-", " ").title()
    out: list[JobResult] = []
    for req in reqs:
        if not isinstance(req, dict):
            continue
        title = (req.get("Title") or "").strip()
        desc = _clean(req.get("ShortDescriptionStr") or "")
        if keyword:
            # The board is fetched keyword-less (whole-board cache); keyword
            # filtering happens here on the title + short description.
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, desc):
                continue
        rid = req.get("Id") or ""
        out.append(JobResult(
            title=title,
            company=company,
            location=_location(req),
            salary_min=None,
            salary_max=None,
            description=desc,
            url=_JOB_URL.format(host=host, site=site, id=rid) if rid else "",
            source_keyword="",
            created=req.get("PostedDate") or "",
            job_id=f"oracleorc_{rid}",
            source_api="careers",
            board_count=board_count,
        ))
    return out
