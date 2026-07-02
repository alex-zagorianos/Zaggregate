"""Auto-detect a company's ATS + slug from a career-page URL, so adding a
company is paste-a-URL instead of knowing greenhouse/lever/workday internals.
Unrecognized hosts fall back to 'direct' (best-effort scrape of the raw URL).

    detect_ats("https://boards.greenhouse.io/acme") -> ("greenhouse", "acme")
    parse_line("Acme | https://jobs.lever.co/acme")  -> CompanyEntry(...)
    probe_count(entry)  -> open-job count (None if uncountable/unreachable)
"""
import re
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
    if ats == "direct":
        host = urlsplit(url if "://" in url else "https://" + url).netloc
        core = host.lower().replace("www.", "").split(".")[0]
        return core.replace("-", " ").title()
    return slug.replace("-", " ").replace("_", " ").title()


def parse_line(line: str) -> CompanyEntry | None:
    """One paste line -> CompanyEntry. Accepts:
       'Name | URL'  ·  bare 'URL' (name derived)  ·  'Name | ats_type | slug'."""
    line = (line or "").strip()
    if not line or line.startswith("#"):
        return None
    parts = [p.strip() for p in line.split("|")]

    if len(parts) >= 3:  # power form: Name | ats_type | slug
        name, ats, slug = parts[0], parts[1].lower(), parts[2]
        return CompanyEntry(name=name or _name_from(ats, slug, slug),
                            ats_type=ats, slug=slug, industries=[])

    if len(parts) == 2:  # Name | URL
        name, url = parts[0], parts[1]
        ats, slug = detect_ats(url)
        return CompanyEntry(name=name or _name_from(ats, slug, url),
                            ats_type=ats, slug=slug, industries=[])

    # "Name, URL" comma form (only when there's no '|'): split on the FIRST comma
    # and treat the remainder as a URL when it looks like one.
    if "," in line:
        name, _, rest = line.partition(",")
        rest = rest.strip()
        if rest and ("http" in rest or "." in rest):
            ats, slug = detect_ats(rest)
            return CompanyEntry(name=name.strip() or _name_from(ats, slug, rest),
                                ats_type=ats, slug=slug, industries=[])

    url = parts[0]       # bare URL
    ats, slug = detect_ats(url)
    return CompanyEntry(name=_name_from(ats, slug, url),
                        ats_type=ats, slug=slug, industries=[])


def probe_count(entry: CompanyEntry) -> int | None:
    """Open-job count for a board (validation). None = uncountable ('direct') or
    unreachable. Keyword-less single request; fail-soft."""
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
            # verify gate and the daily scrape agree on reachability (a CSRF-walled
            # 422 tenant fails the probe here exactly as it will fail the run).
            from scrape.workday_cxs_scraper import fetch as _f
            return len(_f(slug))
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
