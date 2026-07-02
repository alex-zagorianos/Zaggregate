"""Workday `wday/cxs` public JSON scraper (S32 — the marquee-employer unlock).

The `workday_scraper.py` sibling POSTs a per-keyword `searchText` and primes CSRF
with a bare `requests.get`; this fetcher follows the newer S30 oracle/phenom
convention instead: derive {tenant}/{n}/{site} from a careers URL, POST the public
JSON search **keyword-less** so ONE cached whole-board snapshot serves every
keyword in a run, filter locally in `_map`, and route everything through the
shared `careers_session` + per-host limiter (429-safe). A dead tenant is
negative-cached for the FAILED TTL window; a throttle/outage blip is not.

This is the documented public read path that dodges Workday's HTML/CSRF wall for
CSRF-disabled tenants — POST the JSON body instead of GET-ing the HTML page:

    POST https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
      body: {"appliedFacets":{}, "limit":20, "offset":0, "searchText":""}
      -> {"total": T, "jobPostings": [ {job}, ... ]}

Posting shape (validated live 2026-07-02 against mmc.wd1 / nvidia.wd5 / adobe.wd5
/ workday.wd5): each posting carries `title`, `externalPath` (site-relative
"/job/Loc/Title_R123"), `locationsText`, `postedOn` (a RELATIVE label like
"Posted Today", not a date), and `bulletFields` (the reqId is `bulletFields[0]`).
`total` is the whole-board count -> board_count for the scorer's size proxy.

CompanyEntry.slug = "tenant:N:site" (e.g. "cat:5:CaterpillarCareers"), the same
identity the existing workday path uses, so a registry row is portable between
the two. `derive_slug()` turns any Workday careers/CXS URL into that slug.

CAVEAT (per research-sources Headline #1): tenants fronted by Cloudflare/Akamai
bot management (FedEx, AutoZone, Banner, PACCAR, ...) still return HTTP 422 to a
plain HTTP client and cannot be pulled without a real browser fingerprint — the
scraper fails-soft to [] and negative-caches them like any other dead board. The
CSRF-*disabled* tenants (Caterpillar, Marsh McLennan, NVIDIA, Adobe, ...) are the
ones this recovers.
"""
import re
from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CAREERS_SLOW_TIMEOUT
from models import JobResult
from scrape.cache_helpers import is_failed, mark_failed, read_cache, slug_safe, write_cache
from search.http_util import careers_host_limiter, careers_session, host_of

_CXS = "https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
_HOST = "https://{tenant}.wd{n}.myworkdayjobs.com"
_PAGE = 20               # Workday CXS hard per-response cap
_MAX_PAGES = 50          # offset paging ceiling (1000 postings) to bound a run
_LOCALE = re.compile(r"^[a-z]{2}[-_][A-Za-z]{2}$")
_WD_HOST_RE = re.compile(r"^([^.]+)\.wd(\d+)\.myworkdayjobs\.com$", re.I)

try:
    from config import FAILED_TTL_HOURS as _FAILED_TTL
except Exception:
    _FAILED_TTL = 168


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JobSearchTool/1.0",
    }


def _site_from_segs(segs: list[str]) -> str:
    """Extract the careerSite from a public-URL path's segments, skipping an
    optional locale prefix ("en-US") and stopping at a /job/ segment."""
    for s in segs:
        if _LOCALE.match(s):
            continue
        if s.lower() in ("job", "jobs"):
            break
        return s
    return ""


def derive_slug(url: str) -> str:
    """Turn a Workday careers or CXS URL into the "tenant:N:site" slug, or "" if
    the URL is not a recognizable Workday host.

        https://cat.wd5.myworkdayjobs.com/en-US/CaterpillarCareers -> cat:5:CaterpillarCareers
        https://mmc.wd1.myworkdayjobs.com/wday/cxs/mmc/MMC/jobs     -> mmc:1:MMC
    """
    from urllib.parse import urlsplit
    u = (url or "").strip()
    if not u:
        return ""
    if "://" not in u:
        u = "https://" + u
    parts = urlsplit(u)
    host = (parts.netloc or "").lower().split(":")[0]
    m = _WD_HOST_RE.match(host)
    if not m:
        return ""
    tenant, n = m.group(1), m.group(2)
    segs = [s for s in parts.path.split("/") if s]
    # CXS API form: /wday/cxs/{tenant}/{site}/jobs
    if len(segs) >= 4 and segs[0] == "wday" and segs[1] == "cxs":
        site = segs[3]
    else:
        site = _site_from_segs(segs)
    if not site:
        return ""
    return f"{tenant}:{n}:{site}"


def _parse_slug(slug: str) -> Optional[tuple[str, str, str]]:
    """Parse 'tenant:N:site' -> (tenant, n, site). None if malformed."""
    parts = (slug or "").split(":", 2)
    if len(parts) != 3:
        return None
    tenant, n, site = parts
    if not tenant or not n.isdigit() or not site:
        return None
    return tenant, n, site


def _job_url(tenant: str, n: str, site: str, external_path: str) -> str:
    """Build the public posting URL from a CXS externalPath.

    externalPath is site-relative ("/job/Loc/Title_R1") with no site segment, so
    host+externalPath 404s; the browser-facing URL needs the site inserted. Some
    tenants already embed the site (or a locale + site), so only insert when it's
    absent. Mirrors workday_scraper._job_url."""
    if not external_path:
        return ""
    host = _HOST.format(tenant=tenant, n=n)
    if f"/{site}/" in external_path:
        return host + external_path
    return f"{host}/{site}{external_path}"


def fetch(slug: str, *, keyword: str = "",
          cache_dir: Optional[Path] = None, cache_enabled: bool = False,
          company_name: str = "") -> list[JobResult]:
    parsed = _parse_slug(slug)
    if parsed is None:
        print(f"  [workday_cxs] bad slug '{slug}' — expected tenant:N:site")
        return []
    tenant, n, site = parsed

    cache_file = ((cache_dir or CACHE_DIR) / f"workdaycxs_{slug_safe(slug)}.json"
                  if cache_enabled else None)
    failed_file = ((cache_dir or CACHE_DIR) / f"workdaycxs_{slug_safe(slug)}_FAILED.json"
                   if cache_enabled else None)

    if cache_enabled and failed_file is not None:
        if is_failed(read_cache(failed_file, ttl_hours=_FAILED_TTL)):
            return []
        cached = read_cache(cache_file)
        if cached is not None:
            return _map(cached, tenant, n, site, keyword, company_name)

    # Whole-board fetch (keyword-less) so one snapshot serves every keyword; local
    # keyword filtering happens in _map, exactly like oracle_orc / phenom.
    postings, total, permanent = _fetch_all(tenant, n, site)
    if postings is None:
        if cache_enabled and permanent and failed_file is not None:
            mark_failed(failed_file)
        return []
    data = {"total": total, "jobPostings": postings}
    if cache_enabled and cache_file is not None:
        write_cache(cache_file, data)
    return _map(data, tenant, n, site, keyword, company_name)


def _fetch_all(tenant: str, n: str, site: str):
    """Page the CXS jobs endpoint. Returns (postings|None, total, saw_permanent).

    None signals "nothing usable" (first page failed); saw_permanent distinguishes
    a genuinely-dead board (404/410/422 — negative-cache a week) from a transient
    throttle/outage (429/5xx/network — retry next run, never poison)."""
    url = _CXS.format(tenant=tenant, n=n, site=site)
    host = host_of(url)
    all_posts: list[dict] = []
    total = -1
    saw_permanent = False
    for page in range(_MAX_PAGES):
        offset = page * _PAGE
        payload = {"appliedFacets": {}, "limit": _PAGE, "offset": offset, "searchText": ""}
        careers_host_limiter(host).acquire()
        try:
            resp = careers_session().post(url, json=payload, headers=_headers(),
                                          timeout=CAREERS_SLOW_TIMEOUT)
            code = getattr(resp, "status_code", 200)
            if 400 <= code < 500 and code != 429:
                # 404/410/403/422 -> board removed/renamed or CSRF-walled: permanent.
                saw_permanent = True
                if page == 0:
                    print(f"  [workday_cxs] {tenant}:{n}:{site}: HTTP {code} — gone/walled, skipping")
                    return None, total, True
                break
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            if page == 0:
                print(f"  [workday_cxs] {tenant}:{n}:{site}: transient error — {e}")
                return None, total, False
            break
        if not isinstance(body, dict):
            break
        # Trust the FIRST page's total as the authoritative whole-board count:
        # some tenants return total=0 on later (offset>0) pages, which would
        # clobber a good count and zero the scorer's size proxy.
        if page == 0 and isinstance(body.get("total"), int):
            total = body["total"]
        chunk = body.get("jobPostings") or []
        if not chunk:
            break
        all_posts.extend(chunk)
        if len(chunk) < _PAGE:
            break
        if total >= 0 and len(all_posts) >= total:
            break
    if not all_posts and total < 0:
        return [], 0, saw_permanent
    return all_posts, (total if total >= 0 else len(all_posts)), saw_permanent


def _req_id(job: dict) -> str:
    """The reqId lives in bulletFields[0] ("R_353099"); fall back to none."""
    bf = job.get("bulletFields")
    if isinstance(bf, list) and bf and isinstance(bf[0], str):
        return bf[0].strip()
    return ""


def _map(data: dict, tenant: str, n: str, site: str, keyword: str,
         company_name: str = "") -> list[JobResult]:
    posts = data.get("jobPostings") or []
    total = data.get("total")
    board_count = int(total) if isinstance(total, int) and total >= 0 else len(posts)
    # Registry display name first: the tenant slug is an opaque Workday id
    # ("mmc" -> "Mmc"), not the employer ("Marsh McLennan").
    company = (company_name or "").strip() or tenant.replace("-", " ").title()
    out: list[JobResult] = []
    for job in posts:
        if not isinstance(job, dict):
            continue
        title = (job.get("title") or "").strip()
        if not title:
            continue
        # Workday CXS gives no description on the list endpoint; the location text
        # is the only extra signal. Keyword-filter on the title (+ location) so a
        # location-token keyword still works, mirroring the deep matchers.
        loc = (job.get("locationsText") or "").strip()
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, loc):
                continue
        rid = _req_id(job)
        external_path = (job.get("externalPath") or "").strip()
        job_id = f"workdaycxs_{slug_safe(tenant)}_{rid}" if rid else f"workdaycxs_{slug_safe(title)}"
        out.append(JobResult(
            title=title,
            company=company,
            location=loc,
            salary_min=None,
            salary_max=None,
            description="",
            url=_job_url(tenant, n, site, external_path),
            source_keyword="",
            # postedOn is a relative label ("Posted Today"), not an ISO date — pass
            # it through verbatim; the scorer treats an unparseable created as unknown.
            created=(job.get("postedOn") or "").strip(),
            job_id=job_id,
            source_api="careers",
            board_count=board_count,
        ))
    return out
