"""Eightfold (SmartApply) careers scraper (paginated list style).

Endpoint (public career-site XHR, same class as workday_scraper -- a browser
hits it un-authenticated to render the board):
    GET https://{slug}.eightfold.ai/api/apply/v2/jobs?domain={corpdomain}&start=N&num=M&sort_by=relevance
      -> {"count": <total>, "positions": [ {position}, ... ], ...}

The slug is the tenant subdomain (eaton, albemarle, hsbc, ...) and `domain` is
the employer's corporate domain (eaton.com). CompanyEntry.slug encodes BOTH as
"{tenant}:{domain}" (e.g. "eaton:eaton.com") because the domain is a required
query param, not derivable from the subdomain. If no domain is supplied the
subdomain + ".com" is used as a best-effort fallback.

Position shape (validated live 2026-07-01 against albemarle.eightfold.ai):
each position carries `id`, `name` (title), `location`/`locations`,
`department`, `canonicalPositionUrl`, `t_create` (unix seconds),
`display_job_id`, `job_description`. Top-level `count` is the whole-board total.

NOTE (PROVISIONAL for some tenants): a few Eightfold tenants (e.g. Eaton's own
eaton.eightfold.ai as of 2026-07-01) return HTTP 403 "Not authorized for PCSX"
on the public API -- they gate it behind a session/PCS check. Those boards
fail-soft to [] here (a permanent 4xx marks them dead for the TTL window); the
parser itself is validated against the open Albemarle tenant, so a tenant that
DOES answer is handled correctly.

Routed through careers_session + per-host limiter; a Referer header is sent
(some tenants require it) and paging stops at a bounded ceiling. Fail-soft -> [].
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import slug_safe, is_failed, mark_failed, read_cache, write_cache
from scrape.html_text import strip_html_to_text
from search.http_util import careers_host_limiter, careers_session, host_of

_BASE = "https://{tenant}.eightfold.ai/api/apply/v2/jobs"
_PAGE = 50               # positions per request
_MAX_PAGES = 20          # ceiling (1000 positions) to bound a run

# Negative-cache window for a gated/dead tenant (mirrors workday's FAILED file).
try:
    from config import FAILED_TTL_HOURS as _FAILED_TTL
except Exception:
    _FAILED_TTL = 168


def _split_slug(slug: str) -> tuple[str, str]:
    """'tenant:domain' -> (tenant, domain). A bare 'tenant' -> (tenant, tenant.com)."""
    if ":" in slug:
        tenant, domain = slug.split(":", 1)
        return tenant.strip(), domain.strip()
    return slug.strip(), f"{slug.strip()}.com"


def _clean(raw: str) -> str:
    return strip_html_to_text(raw)


def _created(pos: dict) -> str:
    """Unix seconds t_create -> ISO date; '' when absent/unparseable."""
    ts = pos.get("t_create") or pos.get("t_update")
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    return ""


def _location(pos: dict) -> str:
    loc = pos.get("location")
    if isinstance(loc, str) and loc.strip():
        return loc.strip()
    locs = pos.get("locations")
    if isinstance(locs, list) and locs:
        first = locs[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
    return ""


def _headers(tenant: str) -> dict:
    return {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JobSearchTool/1.0",
        "Referer": f"https://{tenant}.eightfold.ai/careers",
    }


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False) -> list[JobResult]:
    tenant, domain = _split_slug(slug)
    if not tenant:
        return []
    url = _BASE.format(tenant=tenant)
    cache_file = ((cache_dir or CACHE_DIR) / f"eightfold_{slug_safe(slug)}.json"
                  if cache_enabled else None)
    failed_file = ((cache_dir or CACHE_DIR) / f"eightfold_{slug_safe(slug)}_FAILED.json"
                   if cache_enabled else None)

    if cache_enabled and failed_file is not None:
        if is_failed(read_cache(failed_file, ttl_hours=_FAILED_TTL)):
            return []
        cached = read_cache(cache_file)
        if cached is not None:
            return _map(cached, tenant, domain, keyword)

    positions, count, permanent = _fetch_all(url, tenant, domain)
    if positions is None:
        if cache_enabled and permanent and failed_file is not None:
            mark_failed(failed_file)
        return []
    data = {"count": count, "positions": positions}
    if cache_enabled and cache_file is not None:
        write_cache(cache_file, data)
    return _map(data, tenant, domain, keyword)


def _fetch_all(url: str, tenant: str, domain: str):
    """Page the board. Returns (positions|None, count, saw_permanent).
    positions=None signals a hard failure (nothing usable)."""
    headers = _headers(tenant)
    all_pos: list[dict] = []
    count = -1
    saw_permanent = False
    for page in range(_MAX_PAGES):
        start = page * _PAGE
        params = {"domain": domain, "start": start, "num": _PAGE, "sort_by": "relevance"}
        careers_host_limiter(host_of(url)).acquire()
        try:
            resp = careers_session().get(url, params=params, headers=headers,
                                         timeout=CAREERS_REQUEST_TIMEOUT)
            code = getattr(resp, "status_code", 200)
            if 400 <= code < 500 and code != 429:
                saw_permanent = True
                if page == 0:
                    print(f"  [eightfold] {tenant}: HTTP {code} — gated/gone, skipping")
                    return None, count, True
                break
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            if page == 0:
                print(f"  [eightfold] {tenant}: transient error — {e}")
                return None, count, False
            break
        if not isinstance(body, dict):
            break
        chunk = body.get("positions") or []
        if isinstance(body.get("count"), int):
            count = body["count"]
        if not chunk:
            break
        all_pos.extend(chunk)
        if len(chunk) < _PAGE:
            break
        if count >= 0 and len(all_pos) >= count:
            break
    if not all_pos and count < 0:
        # First page succeeded but returned nothing parseable and no count:
        # treat as an empty (but reachable) board, not a failure.
        return [], 0, saw_permanent
    return all_pos, (count if count >= 0 else len(all_pos)), saw_permanent


def _map(data: dict, tenant: str, domain: str, keyword: str) -> list[JobResult]:
    positions = data.get("positions") or []
    total = data.get("count")
    board_count = int(total) if isinstance(total, int) and total >= 0 else len(positions)
    company = tenant.replace("-", " ").title()
    out: list[JobResult] = []
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        title = pos.get("name", "") or ""
        dept = pos.get("department", "") or ""
        desc = _clean(pos.get("job_description", "") or "")
        if dept:
            desc = (desc + " " + dept).strip()
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, desc):
                continue
        job_id = pos.get("id") or pos.get("display_job_id") or ""
        job_url = (pos.get("canonicalPositionUrl") or "").strip()
        if not job_url and job_id:
            job_url = f"https://{tenant}.eightfold.ai/careers/job/{job_id}"
        out.append(JobResult(
            title=title,
            company=company,
            location=_location(pos),
            salary_min=None,
            salary_max=None,
            description=desc,
            url=job_url,
            source_keyword="",
            created=_created(pos),
            job_id=f"eightfold_{job_id}",
            source_api="careers",
            board_count=board_count,
        ))
    return out
