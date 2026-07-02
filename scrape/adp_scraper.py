"""ADP Workforce Now public careers scraper (paginated list style).

Endpoint (no-auth public career-center feed; the browser hits it un-
authenticated to render an ADP-hosted careers page):
    GET https://workforcenow.adp.com/mascsr/default/careercenter/public/events/
        staffing/v1/job-requisitions?cid={uuid}&lang=en_US&locale=en_US&$top=N&$skip=M
      -> {"jobRequisitions": [ {req}, ... ], "meta": {"totalNumber": T, ...}}

`cid` is a UUID embedded in an ADP careers link
(workforcenow.adp.com/.../recruitment.html?cid={uuid}); CompanyEntry.slug = that
cid.

Requisition shape (validated live 2026-07-01 against a real public cid):
each req carries `itemID`, `requisitionTitle`, `postDate`, `clientRequisitionID`,
`requisitionLocations` (each with `address.cityName`/`countrySubdivisionLevel1`
and a `nameCode.shortName`), `payGradeRange`. The public list feed carries no
job description body, so `description=""` (v1, same as the workday scraper).
`meta.totalNumber` is the whole-board total, used for paging + the size proxy.

Routed through careers_session + per-host limiter; fail-soft -> []. A public job
detail URL is built from the cid + itemID (the same URL the ADP careers SPA
opens).
"""
from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import slug_safe, is_failed, mark_failed, read_cache, write_cache
from search.http_util import careers_host_limiter, careers_session, host_of

_BASE = ("https://workforcenow.adp.com/mascsr/default/careercenter/public/events/"
         "staffing/v1/job-requisitions")
_PAGE = 200              # $top cap per request
_MAX_PAGES = 25          # ceiling to bound a run (5000 reqs)
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}
_DETAIL = ("https://workforcenow.adp.com/mascsr/default/careercenter/public/index.html"
           "?cid={cid}#/careerCenter/{cid}/requisition/{item}/apply")

try:
    from config import FAILED_TTL_HOURS as _FAILED_TTL
except Exception:
    _FAILED_TTL = 168


def _location(req: dict) -> str:
    locs = req.get("requisitionLocations") or []
    if not isinstance(locs, list) or not locs:
        return ""
    loc = locs[0]
    if not isinstance(loc, dict):
        return ""
    addr = loc.get("address") or {}
    if isinstance(addr, dict):
        city = (addr.get("cityName") or "").strip()
        sub = addr.get("countrySubdivisionLevel1") or {}
        state = (sub.get("codeValue") or sub.get("shortName") or "").strip() if isinstance(sub, dict) else ""
        parts = [p for p in (city, state) if p]
        if parts:
            return ", ".join(parts)
    name = loc.get("nameCode") or {}
    if isinstance(name, dict) and (name.get("shortName") or "").strip():
        return name["shortName"].strip()
    return ""


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False, company_name: str = "") -> list[JobResult]:
    cid = (slug or "").strip()
    if not cid:
        return []
    cache_file = ((cache_dir or CACHE_DIR) / f"adp_{slug_safe(cid)}.json"
                  if cache_enabled else None)
    failed_file = ((cache_dir or CACHE_DIR) / f"adp_{slug_safe(cid)}_FAILED.json"
                   if cache_enabled else None)

    if cache_enabled and failed_file is not None:
        if is_failed(read_cache(failed_file, ttl_hours=_FAILED_TTL)):
            return []
        cached = read_cache(cache_file)
        if cached is not None:
            return _map(cached, cid, keyword, company_name)

    reqs, total, permanent = _fetch_all(cid)
    if reqs is None:
        if cache_enabled and permanent and failed_file is not None:
            mark_failed(failed_file)
        return []
    data = {"jobRequisitions": reqs, "meta": {"totalNumber": total}}
    if cache_enabled and cache_file is not None:
        write_cache(cache_file, data)
    return _map(data, cid, keyword, company_name)


def _fetch_all(cid: str):
    """Page the requisitions. Returns (reqs|None, total, saw_permanent)."""
    all_reqs: list[dict] = []
    total = -1
    saw_permanent = False
    for page in range(_MAX_PAGES):
        skip = page * _PAGE
        params = {"cid": cid, "lang": "en_US", "locale": "en_US",
                  "$top": _PAGE, "$skip": skip}
        careers_host_limiter(host_of(_BASE)).acquire()
        try:
            resp = careers_session().get(_BASE, params=params, headers=_HEADERS,
                                         timeout=CAREERS_REQUEST_TIMEOUT)
            code = getattr(resp, "status_code", 200)
            if 400 <= code < 500 and code != 429:
                saw_permanent = True
                if page == 0:
                    print(f"  [adp] {cid}: HTTP {code} — gone, skipping")
                    return None, total, True
                break
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            if page == 0:
                print(f"  [adp] {cid}: transient error — {e}")
                return None, total, False
            break
        if not isinstance(body, dict):
            break
        chunk = body.get("jobRequisitions") or []
        meta = body.get("meta") or {}
        if isinstance(meta.get("totalNumber"), int):
            total = meta["totalNumber"]
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


def _map(data: dict, cid: str, keyword: str, company_name: str = "") -> list[JobResult]:
    reqs = data.get("jobRequisitions") or []
    total = (data.get("meta") or {}).get("totalNumber")
    board_count = int(total) if isinstance(total, int) and total >= 0 else len(reqs)
    out: list[JobResult] = []
    for req in reqs:
        if not isinstance(req, dict):
            continue
        title = req.get("requisitionTitle", "") or ""
        title = title.strip()
        if keyword:
            from scrape.text_match import keyword_matches
            if not keyword_matches(keyword, title):
                continue
        item = req.get("itemID", "") or ""
        # Real employer name (registry) beats the cid: the slug is an ADP UUID,
        # and title-casing it produced a mangled pseudo-name that also skewed
        # the per-company inbox cap (review finding).
        company = (company_name or "").strip() or cid.replace("-", " ").title()
        out.append(JobResult(
            title=title,
            company=company,
            location=_location(req),
            salary_min=None,
            salary_max=None,
            description="",
            url=_DETAIL.format(cid=cid, item=item) if item else "",
            source_keyword="",
            created=req.get("postDate") or "",
            job_id=f"adp_{item}",
            source_api="careers",
            board_count=board_count,
        ))
    return out
