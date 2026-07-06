"""NSPE Career Center per-keyword RSS -- free, no key, sanctioned public feed.

The National Society of Professional Engineers publishes a keyword-searchable
RSS 2.0 feed on its career center (Naylor/Boxwood platform, no Cloudflare, no
key needed). The feed URL is:

    https://careers.nspe.org/jobs?display=rss&keywords={term}

Verified live 2026-07-05: HTTP 200, ``text/xml;charset=UTF-8``, valid RSS 2.0
(31 items for keywords=mechanical, ~50 unfiltered/no-keyword). Each ``<item>``
carries:
    <title>       "Job Title | Company"  -- split on the LAST " | " (rsplit),
                  so a company name that itself contains " | " is not
                  mis-split. A row with no " | " keeps the whole title and the
                  company is "Unknown" -- NEVER dropped (inclusion over
                  precision).
    <description> starts with a plain-text "City, State, " prefix followed by
                  the job description body (verified live: "Charlotte, North
                  Carolina,  Little is currently seeking a...").
    <pubDate>     RFC-822 date, per item.
    <link>/<guid> detail URL of the shape
                  https://careers.nspe.org/jobs/rss/{numeric_id}/{slug} -- the
                  job_id is extracted from the numeric segment.

US-FOCUSED SOURCE: NSPE is a US professional-engineering society; postings are
overwhelmingly US-based. Non-US seekers get whatever this feed happens to
surface (no location-based skip -- the industry gate below is the only gate),
matching the "never drop, only self-gate on relevance" design.

INDUSTRY GATING: this client self-skips (fetches nothing) unless the active
project's industry is mechanical/manufacturing/industrial-engineering-shaped
(see _terms_for_industry). A nurse's or teacher's project polls no NSPE feeds;
a mechanical/manufacturing/industrial/CAD/mech-design field gets them
automatically -- mirrors industry_profile._RULES' own
{"mechanical","manufacturing","industrial","cad","mechdesign"} rule and the
established HigherEdJobs/RNJobSite token-gate pattern (gate_tokens, not the
raw _tokens, so a plural O*NET title still intersects). That gate is why it is
safe to add to DAILY_SOURCES -- it is inert for every non-mech field.
"""
from typing import Optional

from models import JobResult
from scrape.xml_safe import _safe_fromstring
from search.single_feed_client import SingleFeedClient

NSPE_FEED_URL = "https://careers.nspe.org/jobs?display=rss&keywords={term}"
NSPE_RATE_LIMIT = 5

# Small set of keyword terms to poll -- broad mech/mfg/industrial vocabulary
# covering how postings on this board are actually titled (verified live:
# "Senior Mechanical Engineer", "Manufacturing Engineer", "Industrial
# Engineer" style titles all present under these terms).
NSPE_TERMS: list[str] = [
    "mechanical", "manufacturing", "industrial engineer", "design engineer",
    "mechanical design",
]

# Industry tokens (see industry_profile.gate_tokens) that mean "poll NSPE".
# Any overlap between the project industry's gate tokens and this set
# activates the client. Mirrors industry_profile._RULES' mech/mfg/industrial
# rule so the two stay in lockstep; kept mech/mfg/industrial-specific so a
# nursing/education/trade field never triggers it.
_MECH_TOKENS = frozenset({
    "mechanical", "manufacturing", "industrial", "cad", "mechdesign",
    "mech", "machining", "machinist", "tooling", "fabrication", "npi",
})


def _terms_for_industry(industry: Optional[str]) -> list[str]:
    """The keyword terms to poll for a project's industry, or [] to SELF-SKIP.

    Returns NSPE_TERMS when the industry is mechanical/manufacturing/
    industrial-family (token overlap with _MECH_TOKENS), else []. An empty/
    None industry (Alex's engineering default, and every eng sub-rule EXCEPT
    the mech/mfg/industrial one) returns [] -> the client is inert, so adding
    it to DAILY_SOURCES changes nothing for a non-mech field."""
    import industry_profile
    # gate_tokens (not _tokens) so a PLURAL O*NET title the wizard persists
    # verbatim still intersects the singular gate set -- the same plural-token
    # miss that silenced RNJobSite/HigherEdJobs (scenario finding #2).
    toks = industry_profile.gate_tokens(industry or "")
    if not toks:
        return []
    if toks & _MECH_TOKENS:
        return list(NSPE_TERMS)
    return []


def _split_title_company(title: str) -> tuple[str, str]:
    """NSPE <title> is "Job Title | Company". Split on the LAST " | " (rsplit
    once) so a company name that itself contains " | " isn't mis-split. A
    title with no " | " keeps the whole string as the title and the company
    is "Unknown" -- guard rows missing the delimiter, never drop them."""
    t = (title or "").strip()
    if not t:
        return "", "Unknown"
    if " | " in t:
        job_title, company = t.rsplit(" | ", 1)
        job_title = job_title.strip()
        company = company.strip()
        return (job_title or t), (company or "Unknown")
    return t, "Unknown"


# "City, State, " leading prefix of <description> -- best-effort on the first
# two comma-separated segments. Deliberately conservative: only fires when
# both segments look like plain place-name text (letters/spaces/periods/
# hyphens, no digits) so it never eats into a description that happens to
# start with a comma-bearing sentence. Empty string when it doesn't parse --
# never drop the row for an unparseable location.
import re as _re
_LOCATION_PREFIX_RE = _re.compile(
    r"^\s*([A-Za-z][A-Za-z .'\-]{1,40}),\s*([A-Za-z][A-Za-z .'\-]{1,40}),\s*"
)


def _leading_location(description: str) -> str:
    """Best-effort "City, State" prefix of an NSPE <description>. "" when the
    leading text doesn't look like a plain place name (never drop the row --
    the caller keeps the job with location='' instead)."""
    desc = (description or "")
    m = _LOCATION_PREFIX_RE.match(desc)
    if not m:
        return ""
    city, state = m.group(1).strip(), m.group(2).strip()
    return f"{city}, {state}" if city and state else ""


# .../jobs/rss/<numeric_id>/<slug> -- the numeric segment is the job id.
_JOB_ID_RE = _re.compile(r"/jobs/rss/(\d+)/")


def _job_id_from_link(link: str) -> str:
    m = _JOB_ID_RE.search(link or "")
    return f"nspe_{m.group(1)}" if m else (f"nspe_{link}" if link else "")


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _parse_feed(raw) -> list[dict]:
    """Parse the RSS 2.0 XML into plain dicts (JSON-cacheable).

    RAISES on a malformed/unparseable document (a maintenance page, a CAPTCHA/
    anti-bot HTML response with HTTP 200, a schema change) instead of
    swallowing to [] -- see search.higheredjobs_client._parse_feed's docstring
    for why: the exception must propagate so SingleFeedClient._cached() skips
    the cache write (S35 finding #5) instead of caching a false "empty feed"
    for the full TTL."""
    root = _safe_fromstring(raw)  # XXE/billion-laughs-safe; raises on bad XML
    items = []
    for item in root.iter("item"):
        items.append({
            "title": _text(item, "title"),
            "link": _text(item, "link"),
            "description": _text(item, "description"),
            "pubDate": _text(item, "pubDate"),
        })
    return items


class NspeClient(SingleFeedClient):
    cache_subdir = "nspe"
    rate_limit = NSPE_RATE_LIMIT

    def __init__(self, cache_dir=None, cache_enabled: bool = True,
                 industry: Optional[str] = None):
        super().__init__(cache_dir=cache_dir, cache_enabled=cache_enabled)
        # Resolve the terms to poll ONCE at construction from the active
        # project's industry (explicit arg wins for tests). [] => self-skip.
        if industry is None:
            try:
                from search.source_taxonomy import active_industry
                industry = active_industry()
            except Exception:
                industry = ""
        self.industry = industry or ""
        self.terms = _terms_for_industry(self.industry)

    def _fetch_term(self, term: str) -> list[dict]:
        def fetch():
            self.limiter.acquire()
            url = NSPE_FEED_URL.format(term=term.replace(" ", "+"))
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return {"items": _parse_feed(response.content)}

        from search.http_util import cache_key
        return self._cached(cache_key("nspe", term), fetch).get("items", [])

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        # Single document per term; page>1 has nothing more. Self-skip (no
        # term maps to this industry) returns an empty payload -> 0 jobs.
        if page > 1 or not self.terms:
            return {"items": []}
        # Same posting can appear under multiple polled terms; dedup by link.
        seen: set[str] = set()
        items: list[dict] = []
        for term in self.terms:
            for it in self._fetch_term(term):
                link = it.get("link", "") or ""
                if link and link in seen:
                    continue
                if link:
                    seen.add(link)
                items.append(it)
        return {"items": items, "_location": location or ""}

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        out: list[JobResult] = []
        for item in raw.get("items", []) or []:
            raw_title = (item.get("title", "") or "").strip()
            if not raw_title:
                continue
            title, company = _split_title_company(raw_title)
            # Match on the parsed job title (not the raw "Title | Company"
            # string) so the keyword filter isn't polluted by company names.
            if not keyword_matches(source_keyword, title):
                continue
            location = _leading_location(item.get("description", ""))
            link = item.get("link", "") or ""
            out.append(JobResult(
                title=title,
                company=company,
                location=location,
                salary_min=None,
                salary_max=None,
                description="",
                url=link,
                source_keyword=source_keyword,
                created=item.get("pubDate", "") or "",
                job_id=_job_id_from_link(link),
                source_api="nspe",
            ))
        return out
