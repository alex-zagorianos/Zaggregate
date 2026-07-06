"""Phenom (Phenom People) careers scraper (POST /widgets, list style).

Phenom powers many large employers' career sites (careers.{company}.com). Jobs
are fetched by POSTing to the site's /widgets endpoint with ddoKey=refineSearch.

Endpoint (validated live 2026-07-01 against careers.geaerospace.com):
    POST https://{careers-domain}/widgets
      body: {"lang":"en_us","deviceType":"desktop","country":"us",
             "pageName":"search-results","ddoKey":"refineSearch",
             "size":50,"from":N,"refNum":"{site code}", ...}
      -> {"refineSearch": {"data": {"jobs": [ {job}, ... ], "totalHits": T}}}

`refNum` (e.g. "GAOGAYGLOBAL") identifies the Phenom site and is REQUIRED. It's
scraped ONCE from the site's search-results page HTML (a `"refNum":"..."`
literal) and cached in CompanyEntry.extra["refNum"]; discover_ref_num()
implements that one-time discovery.

CompanyEntry.slug = the careers domain (careers.geaerospace.com);
CompanyEntry.extra = {"refNum": "GAOGAYGLOBAL"}.

Job shape (validated live): each job carries `title`, `cityState`, `jobId`,
`reqId`, `descriptionTeaser`, `postedDate`, `applyUrl`, `category`. totalHits is
sometimes null in the response -> paging stops on a short page instead.

Sitemap fallback: NOT implemented as a live parser here (Phenom sitemaps carry
only URLs, no titles/locations -- a URL-only board is worse than none for
scoring). If /widgets fails the board simply fails-soft to []; this is recorded
as a known limitation. Routed through careers_session + per-host limiter;
fail-soft -> []; a dead domain is negative-cached for the FAILED TTL window.
"""
import json
import re
from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import slug_safe, is_failed, mark_failed, read_cache, write_cache
from scrape.html_text import strip_html_to_text
from search.http_util import careers_host_limiter, careers_session, host_of

_PAGE = 50
_MAX_PAGES = 20          # ceiling (1000 jobs) to bound a run
_REFNUM_RE = re.compile(r'"refNum"\s*:\s*"([A-Za-z0-9_-]+)"')

try:
    from config import FAILED_TTL_HOURS as _FAILED_TTL
except Exception:
    _FAILED_TTL = 168


def _headers(domain: str) -> dict:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JobSearchTool/1.0",
        "Referer": f"https://{domain}/global/en/search-results",
    }


def _body(ref_num: str, from_: int, size: int, keyword: str) -> dict:
    return {
        "lang": "en_us",
        "deviceType": "desktop",
        "country": "us",
        "pageName": "search-results",
        "ddoKey": "refineSearch",
        "size": size,
        "from": from_,
        "talentMatchMinScore": 1,
        "jobs": True,
        "counts": True,
        "all_fields": [],
        "pageType": "searchresults",
        "clearAll": False,
        "jdsource": "facets",
        "isSliderEnable": False,
        "siteType": "external",
        "keywords": keyword or "",
        "global": True,
        "selected_fields": {},
        "sort": {"order": "", "field": ""},
        "locationData": {},
        "s": "1",
        "refNum": ref_num,
    }


def discover_ref_num(domain: str, *, session=None) -> str:
    """One-time refNum discovery from a Phenom search-results page's HTML.

    Returns "" on any failure. Used at onboarding/probe time and cached into
    CompanyEntry.extra["refNum"], so a real daily run never pays this request.
    Polite: single GET through the shared limiter + session.
    """
    domain = (domain or "").strip().lower()
    if not domain:
        return ""
    sess = session or careers_session()
    for path in ("/global/en/search-results", "/us/en/search-results", "/"):
        url = f"https://{domain}{path}"
        careers_host_limiter(domain).acquire()
        try:
            resp = sess.get(url, headers={"User-Agent": _headers(domain)["User-Agent"]},
                            timeout=CAREERS_REQUEST_TIMEOUT)
            if getattr(resp, "status_code", 200) >= 400:
                continue
            m = _REFNUM_RE.search(getattr(resp, "text", "") or "")
            if m:
                return m.group(1)
        except Exception:
            continue
    return ""


def fetch(slug: str, *, keyword: str = "", ref_num: str = "",
          cache_dir: Optional[Path] = None, cache_enabled: bool = False) -> list[JobResult]:
    domain = (slug or "").strip().lower()
    if not domain:
        return []
    ref_num = (ref_num or "").strip()
    if not ref_num:
        ref_num = discover_ref_num(domain)
        if not ref_num:
            print(f"  [phenom] {domain}: no refNum discoverable — skipping")
            return []

    cache_file = ((cache_dir or CACHE_DIR) / f"phenom_{slug_safe(domain)}.json"
                  if cache_enabled else None)
    failed_file = ((cache_dir or CACHE_DIR) / f"phenom_{slug_safe(domain)}_FAILED.json"
                   if cache_enabled else None)

    if cache_enabled and failed_file is not None:
        if is_failed(read_cache(failed_file, ttl_hours=_FAILED_TTL)):
            return []
        cached = read_cache(cache_file)
        if cached is not None:
            return _map(cached, domain, keyword)

    # Whole-board fetch (keyword-less) so one snapshot serves every keyword; local
    # filtering in _map. Keeps the cache keyword-agnostic like the other scrapers.
    jobs, total, permanent = _fetch_all(domain, ref_num, "")
    if jobs is None:
        if cache_enabled and permanent and failed_file is not None:
            mark_failed(failed_file)
        return []
    data = {"totalHits": total, "jobs": jobs}
    if cache_enabled and cache_file is not None:
        write_cache(cache_file, data)
    return _map(data, domain, keyword)


def _fetch_all(domain: str, ref_num: str, keyword: str):
    """Page the widgets endpoint. Returns (jobs|None, total, saw_permanent)."""
    url = f"https://{domain}/widgets"
    headers = _headers(domain)
    all_jobs: list[dict] = []
    total = -1
    saw_permanent = False
    for page in range(_MAX_PAGES):
        from_ = page * _PAGE
        payload = _body(ref_num, from_, _PAGE, keyword)
        careers_host_limiter(host_of(url)).acquire()
        try:
            resp = careers_session().post(url, data=json.dumps(payload), headers=headers,
                                          timeout=CAREERS_REQUEST_TIMEOUT)
            code = getattr(resp, "status_code", 200)
            if 400 <= code < 500 and code != 429:
                saw_permanent = True
                if page == 0:
                    print(f"  [phenom] {domain}: HTTP {code} — gone, skipping")
                    return None, total, True
                break
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            if page == 0:
                print(f"  [phenom] {domain}: transient error — {e}")
                return None, total, False
            break
        rs = (body.get("refineSearch") or {}) if isinstance(body, dict) else {}
        rdata = rs.get("data") or {}
        if isinstance(rdata.get("totalHits"), int):
            total = rdata["totalHits"]
        chunk = rdata.get("jobs") or []
        if not chunk:
            break
        all_jobs.extend(chunk)
        if len(chunk) < _PAGE:
            break
        if total >= 0 and len(all_jobs) >= total:
            break
    if not all_jobs and total < 0:
        return [], 0, saw_permanent
    return all_jobs, (total if total >= 0 else len(all_jobs)), saw_permanent


def _clean(raw: str) -> str:
    return strip_html_to_text(raw)


def _map(data: dict, domain: str, keyword: str) -> list[JobResult]:
    jobs = data.get("jobs") or []
    total = data.get("totalHits")
    board_count = int(total) if isinstance(total, int) and total >= 0 else len(jobs)
    company = domain.replace("careers.", "").replace("jobs.", "").split(".")[0]
    company = company.replace("-", " ").title()
    out: list[JobResult] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = (job.get("title") or "").strip()
        cat = (job.get("category") or "").strip()
        desc = _clean(job.get("descriptionTeaser") or "")
        if cat:
            desc = (desc + " " + cat).strip()
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, desc):
                continue
        jid = job.get("jobId") or job.get("reqId") or ""
        loc = (job.get("cityState") or job.get("location")
               or job.get("cityStateCountry") or "").strip()
        out.append(JobResult(
            title=title,
            company=company,
            location=loc,
            salary_min=None,
            salary_max=None,
            description=desc,
            url=(job.get("applyUrl") or "").strip(),
            source_keyword="",
            created=job.get("postedDate") or job.get("dateCreated") or "",
            job_id=f"phenom_{jid}",
            source_api="careers",
            board_count=board_count,
        ))
    return out
