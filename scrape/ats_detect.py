"""Auto-detect a company's ATS + slug from a career-page URL, so adding a
company is paste-a-URL instead of knowing greenhouse/lever/workday internals.
Unrecognized hosts fall back to 'direct' (best-effort scrape of the raw URL).

    detect_ats("https://boards.greenhouse.io/acme") -> ("greenhouse", "acme")
    parse_line("Acme | https://jobs.lever.co/acme")  -> CompanyEntry(...)
    probe_count(entry)  -> open-job count (None if uncountable/unreachable)
    probe_board(entry)  -> ProbeResult(count, reachable): reachable tells a
                           genuinely-live board (even one with 0 open jobs) from an
                           unreachable one (a 404/410/422 CSRF-walled tenant).
"""
import re
from typing import NamedTuple, Optional
from urllib.parse import urlsplit

from scrape.company_registry import CompanyEntry

_LOCALE = re.compile(r"^[a-z]{2}[-_][A-Za-z]{2}$")
_WD_HOST = re.compile(r"^([^.]+)\.wd(\d+)\.myworkdayjobs\.com$")
_GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _looks_guid(s: str) -> bool:
    """True for a UUID/GUID (Paylocity company id, ADP cid)."""
    return bool(_GUID_RE.match((s or "").strip()))


def _split(url: str):
    u = (url or "").strip()
    if not u:
        return "", [], u
    if "://" not in u:
        u = "https://" + u
    parts = urlsplit(u)
    host = (parts.netloc or "").lower().split(":")[0]
    segs = [s for s in parts.path.split("/") if s]
    return host, segs, u


# Hosts we must NEVER fetch/scrape (ToS-blocked or aggregator/off-board). A
# board on one of these can never legitimately enter the scraped registry — the
# direct scraper would issue a plain requests.get() against them with no per-host
# allowlist. The GUI '+ Add Companies' dialog and (especially) the AI-drivable
# MCP seed_companies path both save 'direct' entries UNPROBED, so an arbitrary
# caller could otherwise seed a fetch target here. Substring-matched against the
# host (so 'www.governmentjobs.com' and 'agency.governmentjobs.com' both hit).
# NEOGOV = governmentjobs.com; Frontline/AppliTrack = applitrack.com/frontline
# (see config.py §Education row, reap_client/edjoin_client module docs).
_TOS_BLOCKED_HOST_SUBSTRINGS = (
    "indeed.com", "governmentjobs.com", "neogov.com", "applitrack.com",
    "frontlineeducation.com", "linkedin.com", "glassdoor.com", "ziprecruiter.com",
    "monster.com",
)


def is_tos_blocked_host(url: str) -> bool:
    """True when *url*'s host is a ToS-blocked or aggregator host we must never
    scrape (NEOGOV/governmentjobs, Frontline/AppliTrack, Indeed, LinkedIn, etc.).
    Used to reject such a URL at parse/save time in the programmatic seed paths
    (apply_seed_lines / MCP seed_companies) so a 'direct' entry can't silently
    become a daily fetch target for one of these hosts."""
    host, _segs, _u = _split(url)
    if not host:
        return False
    return any(b in host for b in _TOS_BLOCKED_HOST_SUBSTRINGS)


def _workday_site(segs: list[str]) -> str:
    # host/wday/cxs/{tenant}/{site}/jobs  (the CXS API URL)
    if len(segs) >= 4 and segs[0] == "wday" and segs[1] == "cxs":
        return segs[3]
    # host/[locale]/SITE[/job/...] (the public URL)
    for s in segs:
        if _LOCALE.match(s):
            continue
        if s.lower() in ("job", "jobs"):
            break
        return s
    return ""


def detect_ats(url: str) -> tuple[str, str]:
    """Return (ats_type, slug). Unrecognized hosts -> ('direct', normalized_url)."""
    host, segs, u = _split(url)
    if not host:
        return ("direct", "")

    if "greenhouse.io" in host:
        if "boards-api" in host and len(segs) >= 3 and segs[:2] == ["v1", "boards"]:
            return ("greenhouse", segs[2])
        if segs:
            return ("greenhouse", segs[0])

    if "lever.co" in host and segs:
        return ("lever", segs[0])

    if "ashbyhq.com" in host:
        if host.endswith(".ashbyhq.com"):
            sub = host[: -len(".ashbyhq.com")]
            if sub and sub not in ("jobs", "api", "www"):
                return ("ashby", sub)
        if segs:
            return ("ashby", segs[0])

    if "smartrecruiters.com" in host and segs:
        return ("smartrecruiters", segs[0])

    m = _WD_HOST.match(host)
    if m:
        site = _workday_site(segs)
        if site:
            # Newly-onboarded Workday URLs use the public wday/cxs JSON reader
            # (workday_cxs_scraper): it POSTs the JSON search body — the documented
            # read path that dodges the HTML/CSRF wall the old "workday" GET-prime
            # path hit with HTTP 422. The slug format ("tenant:N:site") is identical
            # to the legacy "workday" type, so an existing registry row is portable
            # between the two by just relabeling ats_type.
            return ("workday_cxs", f"{m.group(1)}:{m.group(2)}:{site}")

    if host == "apply.workable.com" and segs:
        return ("workable", segs[0])

    if host.endswith(".recruitee.com"):
        sub = host[: -len(".recruitee.com")]
        if sub and sub not in ("www", "api"):
            return ("recruitee", sub)

    for _suffix in (".jobs.personio.de", ".jobs.personio.com"):
        if host.endswith(_suffix):
            sub = host[: -len(_suffix)]
            if sub and sub not in ("www", "api"):
                return ("personio", sub)

    # BambooHR: {slug}.bamboohr.com/careers — the embedded careers-list JSON API
    # lives at {slug}.bamboohr.com/careers/list. slug = the tenant subdomain.
    if host.endswith(".bamboohr.com"):
        sub = host[: -len(".bamboohr.com")]
        if sub and sub not in ("www", "api"):
            return ("bamboohr", sub)

    # Rippling: hosted boards at ats.rippling.com/{slug}; the public board JSON is
    # api.rippling.com/platform/api/ats/v1/board/{slug}/jobs.
    if host == "ats.rippling.com" and segs:
        return ("rippling", segs[0])

    # --- E1: ATS scraper wave 2 ---------------------------------------------
    # Paylocity: recruiting.paylocity.com/recruiting/jobs/All/{guid}/... — the
    # GUID (a long id after /All/ or /jobs/) is the feed key.
    if host == "recruiting.paylocity.com" and segs:
        for i, s in enumerate(segs):
            if s.lower() == "all" and i + 1 < len(segs):
                return ("paylocity", segs[i + 1])
        # Fall back to the last path segment that looks like a GUID.
        for s in reversed(segs):
            if _looks_guid(s):
                return ("paylocity", s)

    # Eightfold: {tenant}.eightfold.ai/careers?domain={corpdomain}. slug encodes
    # BOTH as "tenant:domain" because the domain query param is required.
    if host.endswith(".eightfold.ai"):
        sub = host[: -len(".eightfold.ai")]
        if sub and sub not in ("www", "api", "app"):
            from urllib.parse import parse_qs, urlsplit as _us
            q = parse_qs(_us(u).query)
            dom = (q.get("domain") or [""])[0].strip()
            return ("eightfold", f"{sub}:{dom}" if dom else f"{sub}:{sub}.com")

    # ADP Workforce Now: workforcenow.adp.com/...?cid={uuid}. slug = the cid.
    if host == "workforcenow.adp.com":
        from urllib.parse import parse_qs, urlsplit as _us
        cid = (parse_qs(_us(u).query).get("cid") or [""])[0].strip()
        if cid:
            return ("adp", cid)

    # Oracle Recruiting Cloud (Fusion CandidateExperience): {host}/hcmUI/
    # CandidateExperience/.../sites/{CX_N}/... slug = the host; the CX_N site is
    # carried separately (CompanyEntry.extra["site"]), scraped once from the URL.
    if "oraclecloud.com" in host and "/candidateexperience/" in u.lower():
        return ("oracle_orc", host)

    # Small ATS quartet (subdomain-keyed).
    if host.endswith(".breezy.hr"):
        sub = host[: -len(".breezy.hr")]
        if sub and sub not in ("www", "api"):
            return ("breezy", sub)
    if host.endswith(".pinpointhq.com"):
        sub = host[: -len(".pinpointhq.com")]
        if sub and sub not in ("www", "api"):
            return ("pinpoint", sub)
    if host.endswith(".teamtailor.com"):
        sub = host[: -len(".teamtailor.com")]
        if sub and sub not in ("www", "api"):
            return ("teamtailor", sub)
    if host.endswith(".applytojob.com"):
        sub = host[: -len(".applytojob.com")]
        if sub and sub not in ("www", "api"):
            return ("jazzhr", sub)

    # Phenom: careers.{company}.com search-results page. There is no ATS-owned
    # apex host to fingerprint from a URL alone, so Phenom boards are onboarded
    # explicitly (power form 'Name | phenom | careers.co.com'), not auto-detected
    # here — a bare careers.*.com is far too ambiguous to claim as Phenom.

    # Enterprise ATSes with no open public job-board API (the Cincinnati
    # industrials run these). We can't hit a JSON API, but their career pages
    # carry schema.org/JobPosting JSON-LD (the same data Google for Jobs reads),
    # so tag them and scrape via the generic JSON-LD extractor. slug = the URL.
    if ".icims.com" in host:
        return ("icims", u)
    if ".taleo.net" in host:
        return ("taleo", u)
    if "successfactors.com" in host or ".sapsf." in host:
        return ("successfactors", u)

    return ("direct", u)


def _name_from(ats: str, slug: str, url: str) -> str:
    if ats in ("workday", "workday_cxs") and ":" in slug:
        return slug.split(":")[0].replace("-", " ").title()
    if ats == "vincere":
        # slug is the careers host; the agency name is the domain core.
        from scrape.vincere_scraper import _name_from_host
        return _name_from_host(slug)
    if ats == "direct":
        host = urlsplit(url if "://" in url else "https://" + url).netloc
        core = host.lower().replace("www.", "").split(".")[0]
        return core.replace("-", " ").title()
    return slug.replace("-", " ").replace("_", " ").title()


# ATS types that carry a real, probeable slug — i.e. a resolvable board root
# (as opposed to the 'direct' fallback, which is just the raw URL and can't be
# probed for a live job count). `resolve_board` uses this to decide whether a
# clipped page actually resolved to a job board.
_RESOLVABLE_ATS = frozenset({
    "greenhouse", "lever", "ashby", "smartrecruiters", "workday", "workday_cxs",
    "workable", "recruitee", "personio", "bamboohr", "rippling", "paylocity",
    "eightfold", "adp", "oracle_orc", "phenom", "breezy", "pinpoint",
    "teamtailor", "jazzhr", "icims", "taleo", "successfactors", "jsonld",
    "vincere",
})


def _detect_vincere(url: str, probe_fn=None) -> tuple[str, str] | None:
    """When URL-only detection can't identify the ATS (a Vincere board lives on
    the agency's own careers.<agency>.com, indistinguishable from any careers
    page by host alone), PROBE the page for the Vincere fingerprint
    (static.vincere.io assets). Returns ("vincere", host) on a match, else None.

    Never probes a ToS-blocked host (the guard runs first). ``probe_fn`` (host ->
    bool) is injectable so tests need no network; it defaults to the live
    fingerprint probe in vincere_scraper."""
    if is_tos_blocked_host(url):
        return None
    if probe_fn is None:
        from scrape.vincere_scraper import is_vincere_host as probe_fn
    from scrape.vincere_scraper import derive_slug as _vslug
    host = _vslug(url)
    if not host:
        return None
    try:
        if probe_fn(url):
            return ("vincere", host)
    except Exception:
        return None
    return None


def resolve_board(url: str, page_title: str = "", *, vincere_probe=None):
    """Resolve a *job-posting or board* URL to its board root for clip-to-seed.

    Returns a dict:
        {"resolvable": bool, "ats_type": str, "slug": str, "name": str}

    Reuses ``detect_ats`` (which already strips a posting's job-id path back to
    the board root for greenhouse/lever/ashby/smartrecruiters/workday_cxs, so a
    user clipping a live *posting* seeds the whole board, not one job). The
    board is *resolvable* only when detection lands on a recognized ATS with a
    real slug — the ``('direct', url)`` fallback (an unrecognized host, e.g. a
    generic company careers page or an off-board page like a search result) is
    NOT resolvable, because it has no probeable JSON board and clipping it would
    just dump the raw URL into the registry unverified. A page title, when the
    extension sends one, gives the board a human name over the slug-derived one.

    ONE URL-opaque ATS is resolved by PROBING when detection falls back to
    'direct': Vincere quick-job-boards (careers.<agency>.com) can't be told from
    a generic careers page by host, so we fetch the page and fingerprint
    static.vincere.io. ``vincere_probe`` (host -> bool) is injectable for tests;
    the ToS-blocked-host guard in detect_ats/_detect_vincere runs BEFORE it, so a
    blocked host is never probed and never resolves to vincere.

    This is deliberately stricter than the paste-a-URL '+ Add Companies' dialog
    (which treats a 'direct' careers page as verified-manual): a one-click clip
    must only auto-seed a board we can actually verify live at clip time — that
    is the whole point of clip-to-seed (competitors §8C), so an unverifiable
    page returns resolvable=False and the caller reports a clear failure rather
    than silently saving junk.

    Board name comes from the ATS slug (clean: 'acme' -> 'Acme'), NOT the page
    title — a clipped posting's <title> is usually the *job* title with board
    chrome ('Software Engineer - Acme | Lever'), which would both mis-name the
    board and, because save_companies dedups by name, defeat duplicate-clip
    detection. The page title is only a last-resort fallback when the derived
    name is empty."""
    ats, slug = detect_ats(url)
    if ats == "direct":
        # URL-only detection couldn't name the ATS. Probe for Vincere before
        # giving up (a Vincere board is a real, verifiable, scrapeable board — it
        # just isn't identifiable from the host). The ToS guard runs inside.
        vin = _detect_vincere(url, probe_fn=vincere_probe)
        if vin is not None:
            ats, slug = vin
    resolvable = ats in _RESOLVABLE_ATS and bool(slug)
    name = _name_from(ats, slug, url) or (page_title or "").strip()
    return {"resolvable": resolvable, "ats_type": ats, "slug": slug, "name": name}


# A leading markdown/list marker ("- ", "* ", "• ", "1. ", "2) ") a weak AI adds.
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
# The first http(s) URL anywhere in a line (stops at whitespace / pipe / bracket).
_URL_RE = re.compile(r"https?://[^\s|,)\]>]+", re.I)


def parse_line(line: str) -> CompanyEntry | None:
    """One paste line -> CompanyEntry, or None to DROP the line. Accepts:
       'Name | URL'  ·  bare 'URL' (name derived)  ·  'Name | ats_type | slug'.

    Hardened for weak-AI formatting (S35): strips a leading list marker ('- ',
    '1. ') and markdown bold, then requires a real http URL for any non-power
    line. A line with NO URL is prose the AI wrapped around the list ("Here are
    some employers:") — dropped, NOT saved as a junk 'direct' company. A bulleted
    or numbered careers URL is rescued: the embedded URL is extracted and routed
    through detect_ats so its ATS slug is recovered instead of mangled."""
    line = (line or "").strip()
    if not line or line.startswith("#"):
        return None
    line = _LIST_MARKER_RE.sub("", line, count=1)
    line = line.replace("**", "").strip()          # drop markdown bold on name
    if not line:
        return None
    parts = [p.strip() for p in line.split("|")]

    if len(parts) >= 3:  # power form: Name | ats_type | slug (explicit; kept as-is)
        name, ats, slug = parts[0], parts[1].lower(), parts[2]
        return CompanyEntry(name=name or _name_from(ats, slug, slug),
                            ats_type=ats, slug=slug, industries=[])

    # Every other accepted form must contain a real URL. Extract the FIRST one
    # anywhere in the line (rescues "Name: URL", "Name - URL", bullets, numbers).
    m = _URL_RE.search(line)
    if not m:
        return None                                 # no URL -> prose, drop it
    url = m.group(0).rstrip(".")                     # trailing sentence period
    ats, slug = detect_ats(url)

    if len(parts) == 2:                              # Name | URL
        name = parts[0]
    else:                                            # "Name: URL" / "Name - URL" / bare URL
        name = line[:m.start()].strip(" \t-:,–—")
    return CompanyEntry(name=name or _name_from(ats, slug, url),
                        ats_type=ats, slug=slug, industries=[])


class ProbeResult(NamedTuple):
    """Richer probe verdict than a bare count, so the P0-6 verify gate can tell a
    genuinely-live board from an unreachable one.

    ``count``     : open-job count (int, possibly 0) when the board was READ; None
                    when it could not be counted (uncountable 'direct', or the read
                    itself failed).
    ``reachable`` : True only when the scraper actually READ the board this probe.
                    A live board with 0 open jobs is reachable=True, count=0 — that
                    is a VERIFIED-but-empty state. A CSRF/Cloudflare-walled Workday
                    tenant (HTTP 422/404/410) is reachable=False, count=None — it
                    must land in the SAME unreachable bucket as any dead board
                    (kept-unverified, excluded from scraping, re-verify path applies
                    if it ever opens up). This is the distinction a bare count lost:
                    a walled workday_cxs probe fail-softs to [] -> len([])==0, an
                    int, which the old gate mistook for "live (0 open jobs)"."""
    count: Optional[int]
    reachable: bool


def probe_board(entry: CompanyEntry) -> ProbeResult:
    """Probe a board and return BOTH its open-job count and whether it was actually
    reachable (readable) this probe — the signal the verify gate needs to keep a
    walled board out of the 'verified' bucket.

    Reachability rules, consistent across ATS types:
      * 'direct' (raw careers URL, no probeable JSON board): count=None,
        reachable=False — uncountable. Callers that treat a user-supplied direct
        page as verified-manual special-case ats_type=='direct' BEFORE probing;
        this function does not claim a direct page is live.
      * A count-API ATS (greenhouse/lever/ashby/smartrecruiters/rippling/bamboohr):
        an HTTP-200 read returns the count (0 is a live-but-empty board =>
        reachable); any non-2xx / parse failure fail-softs to count=None =>
        NOT reachable. So for these reachable == (count is not None).
      * workday_cxs: routed through workday_cxs_scraper.fetch_with_status, which
        distinguishes a clean 200 read (STATUS_OK — reachable, count may be 0) from
        a permanent 422/404/410 wall (STATUS_PERMANENT — NOT reachable) or a
        transient blip (STATUS_TRANSIENT — NOT reachable, retry next run). This is
        the case the smoke test caught: 14/15 marquee tenants 422-walled but saved
        as "verified (0 jobs)". They are now correctly unreachable.
      * Other scraper-backed probes (paylocity/eightfold/adp/oracle/phenom/breezy/
        pinpoint/teamtailor/jazzhr, and JSON-LD icims/taleo/successfactors) return
        len(fetch(...)); a 200-empty board and a soft-failed fetch both yield 0, so
        for these reachable == (count is not None) — a 0-count is treated as
        live-but-empty (verified), matching the greenhouse-200-empty semantics.
        Only workday_cxs carries a wall (422) that must not read as verified-empty.
    """
    t = (entry.ats_type or "").strip().lower()
    if t == "direct":
        # Uncountable: the raw careers URL has no probeable board.
        return ProbeResult(None, False)
    if t == "workday_cxs" and (entry.slug or "").count(":") == 2:
        try:
            from scrape.cache_helpers import STATUS_OK
            from scrape.workday_cxs_scraper import fetch_with_status
            jobs, status = fetch_with_status(entry.slug)
        except Exception:
            return ProbeResult(None, False)
        if status == STATUS_OK:
            # Read succeeded — 0 postings means a live board with 0 open jobs
            # (VERIFIED-empty), NOT a wall.
            return ProbeResult(len(jobs), True)
        # STATUS_PERMANENT (walled/gone) or STATUS_TRANSIENT (blip): unreachable.
        return ProbeResult(None, False)
    if t == "vincere":
        # Vincere board (slug = careers host): the public /ajax/search-jobs read
        # via the production fetcher, so probe and daily scrape agree on
        # reachability. STATUS_OK = read (count may be 0 = live-empty); a
        # robots-Disallow/gone (PERMANENT) or blip (TRANSIENT) is unreachable.
        try:
            from scrape.cache_helpers import STATUS_OK
            from scrape.vincere_scraper import fetch_with_status as _vfs
            jobs, status = _vfs(entry.slug)
        except Exception:
            return ProbeResult(None, False)
        if status == STATUS_OK:
            return ProbeResult(len(jobs), True)
        return ProbeResult(None, False)
    # Everything else: reuse the count probe; reachable iff we got a real count.
    n = probe_count(entry)
    return ProbeResult(n, n is not None)


def probe_count(entry: CompanyEntry) -> int | None:
    """Open-job count for a board (validation). None = uncountable ('direct') or
    unreachable. Keyword-less single request; fail-soft.

    NOTE: a bare count cannot distinguish a live-but-empty board (0 open jobs) from
    a CSRF-walled one that fail-softs to []. Consumers that make verify decisions
    should call ``probe_board`` (which carries a ``reachable`` flag) instead. This
    function is kept for callers that only need the count (and for the count of the
    ATS types where 0 unambiguously means live-empty)."""
    import requests
    from config import CAREERS_REQUEST_TIMEOUT as TO
    try:
        t, slug = entry.ats_type, entry.slug
        if t == "greenhouse":
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=TO)
            if r.ok:
                d = r.json()
                return d.get("meta", {}).get("total", len(d.get("jobs", [])))
        elif t == "lever":
            r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=TO)
            if r.ok:
                return len(r.json())
        elif t == "ashby":
            r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=TO)
            if r.ok:
                return len(r.json().get("jobs", []))
        elif t == "smartrecruiters":
            r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1", timeout=TO)
            if r.ok:
                return r.json().get("totalFound")
        elif t == "workday" and slug.count(":") == 2:
            tenant, n, site = slug.split(":")
            r = requests.post(
                f"https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
                json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=TO)
            if r.ok:
                return r.json().get("total")
        elif t == "workday_cxs" and slug.count(":") == 2:
            # Same public cxs POST, but count via the production fetcher so the
            # verify gate and the daily scrape agree on reachability. A CSRF-walled
            # 422 tenant (STATUS_PERMANENT) or a transient blip returns None here —
            # NOT a false 0 — so a bare-count caller can't mistake a wall for a
            # live-but-empty board. A clean 200 read returns the count (0 = live
            # board with 0 open jobs). See probe_board for the richer verdict.
            from scrape.cache_helpers import STATUS_OK
            from scrape.workday_cxs_scraper import fetch_with_status as _fs
            jobs, status = _fs(slug)
            return len(jobs) if status == STATUS_OK else None
        elif t == "vincere":
            # Public /ajax/search-jobs read via the production fetcher; a
            # robots-Disallow/gone (PERMANENT) or blip (TRANSIENT) returns None
            # (fail-soft), never a false 0. A clean 200 read returns the count.
            from scrape.cache_helpers import STATUS_OK
            from scrape.vincere_scraper import fetch_with_status as _vfs2
            jobs, status = _vfs2(slug)
            return len(jobs) if status == STATUS_OK else None
        elif t == "bamboohr":
            # Embedded careers-list JSON. Use the SAME headers the production
            # scraper (bamboohr_scraper) sends, so the verify-gate and the daily
            # scrape agree on reachability (a UA mismatch here would let a board
            # verify at onboarding then silently 403 on every real run, or the
            # reverse). A failed probe returns None (fail-soft), never a false 0.
            from scrape.bamboohr_scraper import _HEADERS as _BAMBOO_HEADERS
            r = requests.get(f"https://{slug}.bamboohr.com/careers/list", timeout=TO,
                             headers=_BAMBOO_HEADERS)
            if r.ok:
                return len(r.json().get("result", []))
        elif t == "rippling":
            r = requests.get(
                f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs",
                timeout=TO, headers={"Accept": "application/json",
                                     "User-Agent": "JobSearchTool/1.0 (personal use)"})
            if r.ok:
                d = r.json()
                return len(d if isinstance(d, list) else d.get("items", []) or [])
        elif t == "paylocity":
            from scrape.paylocity_scraper import fetch as _f
            return len(_f(slug))
        elif t == "eightfold":
            from scrape.eightfold_scraper import fetch as _f
            return len(_f(slug))
        elif t == "adp":
            from scrape.adp_scraper import fetch as _f
            return len(_f(slug))
        elif t == "oracle_orc":
            # host in slug; siteNumber in entry.extra (discovered once if absent).
            from scrape.oracle_orc_scraper import fetch as _f
            return len(_f(slug, site=(entry.extra or {}).get("site", "")))
        elif t == "phenom":
            from scrape.phenom_scraper import fetch as _f
            return len(_f(slug, ref_num=(entry.extra or {}).get("refNum", "")))
        elif t == "breezy":
            from scrape.breezy_scraper import fetch as _f
            return len(_f(slug))
        elif t == "pinpoint":
            from scrape.pinpoint_scraper import fetch as _f
            return len(_f(slug))
        elif t == "teamtailor":
            from scrape.teamtailor_scraper import fetch as _f
            return len(_f(slug))
        elif t == "jazzhr":
            from scrape.jazzhr_scraper import fetch as _f
            return len(_f(slug))
        elif t in ("icims", "taleo", "successfactors", "jsonld"):
            # JSON-LD-backed boards (no count API): count schema.org/JobPosting
            # entries on the career page. 0 when the page hides them behind
            # JS/bot-protection — best-effort, so the verify gate stays honest.
            from scrape.jsonld_scraper import extract_jobs
            r = requests.get(slug, timeout=TO, headers={"User-Agent": "Mozilla/5.0"})
            if r.ok:
                return len(extract_jobs(r.text, slug))
    except Exception:
        return None
    return None
