"""Vincere "quick job board" public-JSON scraper (S34 — a whole ATS class).

Vincere (vincere.io) hosts recruiting-agency job boards on the agency's OWN
domain (careers.<agency>.com), so the careers-subdomain URL alone can't identify
the ATS — the fingerprint is in the page HTML (assets served from
``static.vincere.io``, e.g. ``static.vincere.io/img/qjb-fav.png`` and a
``quick-job-board/<board>-vincere-io/`` logo path). Many staffing/recruiting
agencies run one (Edison Smart's careers.edisonsmart.com lists 214 jobs).

The board loads its jobs via a same-origin XHR the page fires on search:

    GET  https://{host}/                      -> HTML carries a Laravel CSRF
                                                 `_token` + sets XSRF-TOKEN /
                                                 laravel_session cookies
    POST https://{host}/ajax/search-jobs      (form-encoded, needs the _token +
      body: _token, keywords, location, unit, radius, page, schedule
      -> 200 JSON {"total": T, "more": bool, "items": [ {job}, ... ],
                   "facets": {...}, "html": "..."}

The `items` array is the clean structured payload (the `html` key is the same
data pre-rendered for the page); each item carries `id`, `job_title`,
`location` (a dict: address / city / state / country / country_code /
location_name), `salary_from` / `salary_to` (+ formatted_* + salary_type;
"0.0"/"USD $0.00" means unset), `published_date` (ISO), `close_date`,
`job_type`, `employment_type`, and `public_description` (HTML). The browser
posting URL is `{host}/job/{id}/{slug}`; `total` is the whole-board count ->
board_count for the scorer's size proxy, and the ProbeResult reachability total.

Like oracle_orc / phenom / workday_cxs, this fetches the board KEYWORD-LESS so
ONE cached whole-board snapshot serves every keyword in a run, filtering locally
in `_map`. It follows the same 429-safe conventions: the shared careers_session
(so the GET's session cookies carry into the POST) + per-host limiter, a dead
host negative-cached for the FAILED TTL window, a throttle/outage blip not.

CompanyEntry.slug = the careers host (e.g. "careers.edisonsmart.com") — a
registry row is identified by the host the user clipped. `derive_slug()` turns
any Vincere board/posting URL into that host.

ROBOTS: honored per-host (reap_client / direct_scraper precedent). If a host's
robots.txt explicitly Disallows the ajax path, the fetch fails-soft to [] with a
single log line — the machinery is built, but that host is skipped. robots.txt
has no binding legal force, so a fetch/parse hiccup fails OPEN (edisonsmart's is
`User-agent: * / Disallow:` = fully permissive).

CAPTCHA: the page loads reCAPTCHA v3 (invisible, score-based) around the search,
but the server does NOT enforce the captcha token on /ajax/search-jobs — a POST
with a valid `_token` + session cookie returns 200 JSON (validated live
2026-07-02 against careers.edisonsmart.com, 214 jobs). We send an honest UA and
the CSRF token the page itself issues; we never solve or spoof the captcha.
"""
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from config import CACHE_DIR, CAREERS_SLOW_TIMEOUT
from models import JobResult
from scrape.cache_helpers import (
    STATUS_OK,
    STATUS_PERMANENT,
    STATUS_TRANSIENT,
    is_failed,
    mark_failed,
    read_cache,
    slug_safe,
    write_cache,
)
from search.http_util import careers_host_limiter, careers_session, host_of

_AJAX = "https://{host}/ajax/search-jobs"
_PAGE_URL = "https://{host}/"
_JOB_URL = "https://{host}/job/{id}/{slug}"
_PER_PAGE = 10            # the board returns 10 items/page (its `more` flag paginates)
_MAX_PAGES = 60          # ceiling (~600 postings) so one bad board can't run away
_TOKEN_RE = re.compile(r'name="_token"[^>]*value="([^"]+)"')
# static.vincere.io asset references are the reliable Vincere fingerprint in the
# board HTML (favicon + the quick-job-board logo path); the brand token varies.
_FINGERPRINT_RE = re.compile(r"static\.vincere\.io|quick-job-board/[^\"'/]+-vincere-io/", re.I)
_TAG_RE = re.compile(r"<[^>]+>")

try:
    from config import FAILED_TTL_HOURS as _FAILED_TTL
except Exception:
    _FAILED_TTL = 168


def _headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JobSearchTool/1.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }


def _page_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JobSearchTool/1.0",
        "Accept": "text/html,application/xhtml+xml",
    }


def derive_slug(url: str) -> str:
    """Turn a Vincere careers/board/posting URL into its host slug, or "" if the
    URL has no host.

        https://careers.edisonsmart.com/?unit=mile&radius=50&page=1  -> careers.edisonsmart.com
        https://careers.edisonsmart.com/job/252557/senior-engineer   -> careers.edisonsmart.com
    """
    u = (url or "").strip()
    if not u:
        return ""
    if "://" not in u:
        u = "https://" + u
    host = (urlsplit(u).netloc or "").lower().split(":")[0]
    return host


def looks_like_vincere(html: str) -> bool:
    """True when a fetched careers-page HTML carries the Vincere fingerprint
    (static.vincere.io assets / the quick-job-board logo path). The careers host
    can't identify Vincere on its own, so detection PROBES the page and matches
    this."""
    return bool(html) and bool(_FINGERPRINT_RE.search(html))


def is_vincere_host(host_or_url: str) -> bool:
    """Probe a careers host/URL: GET the page and fingerprint the HTML. Fail-soft
    to False on any network/parse error (an unreachable page is not claimable as
    Vincere). Routed through the shared session + per-host limiter like a fetch."""
    slug = derive_slug(host_or_url)
    if not slug:
        return False
    html, _status = _get_page_html(slug)
    return looks_like_vincere(html or "")


def _get_page_html(host: str) -> tuple[Optional[str], str]:
    """GET the board landing page. Returns (html|None, status). Used both to
    fingerprint (detection) and to mint the CSRF token + session cookies before
    the ajax POST."""
    url = _PAGE_URL.format(host=host)
    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, headers=_page_headers(),
                                     timeout=CAREERS_SLOW_TIMEOUT)
        code = getattr(resp, "status_code", 200)
        if 400 <= code < 500 and code != 429:
            return None, STATUS_PERMANENT
        resp.raise_for_status()
        return resp.text, STATUS_OK
    except Exception:
        return None, STATUS_TRANSIENT


def _robots_ok(host: str) -> bool:
    """Good-faith robots.txt check on the ajax path (reap_client / direct_scraper
    precedent). Returns False only when robots.txt EXPLICITLY Disallows it; any
    unreachable/malformed robots.txt fails OPEN (True) — robots has no binding
    legal force and a hiccup must never block a working board."""
    try:
        from discover.career_link import is_disallowed
        return not is_disallowed(_AJAX.format(host=host))
    except Exception:
        return True


def fetch(slug: str, *, keyword: str = "",
          cache_dir: Optional[Path] = None, cache_enabled: bool = False,
          company_name: str = "") -> list[JobResult]:
    """Back-compat: return just the mapped postings (drops the status class)."""
    jobs, _status = fetch_with_status(
        slug, keyword=keyword, cache_dir=cache_dir,
        cache_enabled=cache_enabled, company_name=company_name)
    return jobs


def fetch_with_status(slug: str, *, keyword: str = "",
                      cache_dir: Optional[Path] = None, cache_enabled: bool = False,
                      company_name: str = "") -> tuple[list[JobResult], str]:
    """Public Vincere board fetch that also returns the reachability status class
    (mirrors workday_cxs_scraper.fetch_with_status):

      - STATUS_OK        : the board was READ (HTTP 200). 0 items = a live board
                           with 0 open jobs (VERIFIED-empty), not unreachable.
      - STATUS_PERMANENT : a hard 4xx (page/ajax gone) OR robots.txt Disallows the
                           ajax path for this host — the scraper can't/shouldn't
                           read it, so "verified" would be a lie; treat UNREACHABLE.
      - STATUS_TRANSIENT : a 429/5xx/network blip or a missing CSRF token — not a
                           wall, retry next run, NOT verified this pass.

    A cache HIT is STATUS_OK; a fresh negative-cache marker is STATUS_PERMANENT so
    the verdict stays stable across the negative-cache window."""
    host = derive_slug(slug)
    if not host:
        return [], STATUS_PERMANENT

    cache_file = ((cache_dir or CACHE_DIR) / f"vincere_{slug_safe(host)}.json"
                  if cache_enabled else None)
    failed_file = ((cache_dir or CACHE_DIR) / f"vincere_{slug_safe(host)}_FAILED.json"
                   if cache_enabled else None)

    if cache_enabled and failed_file is not None:
        if is_failed(read_cache(failed_file, ttl_hours=_FAILED_TTL)):
            return [], STATUS_PERMANENT
        cached = read_cache(cache_file)
        if cached is not None:
            return (_map(cached, host, keyword, company_name), STATUS_OK)

    # robots gate (per-host): an explicit Disallow of the ajax path -> skip this
    # host with a single log line, negative-cache it like a wall.
    if not _robots_ok(host):
        print(f"  [vincere] {host}: robots.txt disallows /ajax/search-jobs — skipping")
        if cache_enabled and failed_file is not None:
            mark_failed(failed_file)
        return [], STATUS_PERMANENT

    items, total, status = _fetch_all(host)
    if items is None:
        if cache_enabled and status == STATUS_PERMANENT and failed_file is not None:
            mark_failed(failed_file)
        return [], status
    data = {"total": total, "items": items}
    if cache_enabled and cache_file is not None:
        write_cache(cache_file, data)
    return (_map(data, host, keyword, company_name), STATUS_OK)


def _fetch_all(host: str):
    """Drive the Vincere ajax search. Returns (items|None, total, status).

    ``items`` is None only when the FIRST usable read failed (nothing usable).
    The Laravel endpoint needs the page's `_token` + session cookies, so we GET
    the landing page once (on the shared session that persists cookies) to mint
    them, then POST keyword-less, paginating on the response `more` flag."""
    # 1) Landing page -> CSRF token + session cookies (persisted on careers_session).
    html, page_status = _get_page_html(host)
    if html is None:
        return None, -1, page_status
    m = _TOKEN_RE.search(html)
    if not m:
        # No CSRF token to send -> the ajax POST would 419 (Page Expired). Treat
        # as transient (a page-shape change), not a permanent wall.
        print(f"  [vincere] {host}: no CSRF token on landing page — skipping")
        return None, -1, STATUS_TRANSIENT
    token = m.group(1)

    ajax_url = _AJAX.format(host=host)
    limiter_host = host_of(ajax_url)
    all_items: list[dict] = []
    total = -1
    for page in range(1, _MAX_PAGES + 1):
        payload = {
            "_token": token,
            "keywords": "",
            "location": "",
            "unit": "mile",
            "radius": "50",
            "page": str(page),
            "schedule": "daily",
        }
        careers_host_limiter(limiter_host).acquire()
        try:
            resp = careers_session().post(ajax_url, data=payload, headers=_headers(),
                                          timeout=CAREERS_SLOW_TIMEOUT)
            code = getattr(resp, "status_code", 200)
            if 400 <= code < 500 and code != 429:
                if page == 1:
                    print(f"  [vincere] {host}: HTTP {code} on ajax — gone/walled, skipping")
                    return None, total, STATUS_PERMANENT
                break
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            if page == 1:
                print(f"  [vincere] {host}: transient error — {e}")
                return None, total, STATUS_TRANSIENT
            break
        if not isinstance(body, dict):
            break
        if page == 1 and isinstance(body.get("total"), int):
            total = body["total"]
        chunk = body.get("items") or []
        if not isinstance(chunk, list) or not chunk:
            break
        all_items.extend(chunk)
        if not body.get("more"):
            break
        if total >= 0 and len(all_items) >= total:
            break
    if not all_items and total < 0:
        return [], 0, STATUS_OK
    return all_items, (total if total >= 0 else len(all_items)), STATUS_OK


def _num(v) -> Optional[float]:
    """Vincere salary fields are strings ("120000.0"); "0.0"/0 means unset."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _location(loc) -> str:
    """Best human location string from the item's location dict."""
    if not isinstance(loc, dict):
        return ""
    for key in ("location_name", "address"):
        v = (loc.get(key) or "").strip()
        if v:
            return v
    # Compose from parts as a last resort.
    parts = [p for p in (loc.get("city"), loc.get("state"), loc.get("country")) if p]
    return ", ".join(p.strip() for p in parts if str(p).strip())


def _strip_html(s: str) -> str:
    """public_description is HTML; flatten to text for the scorer/matcher."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", s)).strip()


def _map(data: dict, host: str, keyword: str, company_name: str = "") -> list[JobResult]:
    items = data.get("items") or []
    total = data.get("total")
    board_count = int(total) if isinstance(total, int) and total >= 0 else len(items)
    # The board host names the agency ("careers.edisonsmart.com" -> "Edisonsmart");
    # the registry display name (when present) wins.
    company = (company_name or "").strip() or _name_from_host(host)
    out: list[JobResult] = []
    for job in items:
        if not isinstance(job, dict):
            continue
        title = (job.get("job_title") or "").strip()
        if not title:
            continue
        loc = _location(job.get("location"))
        desc = _strip_html(job.get("public_description") or "")
        if keyword:
            from scrape.text_match import keyword_matches_deep
            # body = location + description so a location-token keyword still
            # matches (mirrors the deep matchers on the other whole-board fetchers).
            if not keyword_matches_deep(keyword, title, f"{loc} {desc}"):
                continue
        jid = job.get("id")
        job_slug = _url_slug(title)
        url = (_JOB_URL.format(host=host, id=jid, slug=job_slug)
               if jid is not None else "")
        out.append(JobResult(
            title=title,
            company=company,
            location=loc,
            salary_min=_num(job.get("salary_from")),
            salary_max=_num(job.get("salary_to")),
            description=desc,
            url=url,
            source_keyword="",
            created=(job.get("published_date") or "").strip(),
            job_id=f"vincere_{slug_safe(host)}_{jid}" if jid is not None
            else f"vincere_{slug_safe(title)}",
            source_api="careers",
            board_count=board_count,
            # close_date is the publisher-declared expiry when present (ISO); the
            # ghost/stale matcher treats a past validThrough as the strongest
            # stale signal. Absent -> "" (abstain).
            valid_through=(job.get("close_date") or "").strip(),
        ))
    return out


def _url_slug(title: str) -> str:
    """A URL-friendly slug from the job title, matching Vincere's posting URLs
    (`/job/{id}/{slug}`). The id already uniquely identifies the posting server-
    side, so the slug is cosmetic — a stable derivation keeps URLs deterministic."""
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return s or "job"


def _name_from_host(host: str) -> str:
    """Agency display name from the careers host: careers.edisonsmart.com ->
    "Edisonsmart" (strip a leading careers/jobs/www label + the TLD)."""
    core = (host or "").lower()
    for pre in ("careers.", "jobs.", "www.", "apply."):
        if core.startswith(pre):
            core = core[len(pre):]
            break
    core = core.split(".")[0]
    return core.replace("-", " ").title()
