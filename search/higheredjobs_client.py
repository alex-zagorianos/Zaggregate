"""HigherEdJobs per-category RSS — free, no key, sanctioned public feeds.

HigherEdJobs publishes one RSS 2.0 feed per job category. The feed URL is:

    https://www.higheredjobs.com/rss/categoryFeed.cfm?catID={id}

(NOTE: an earlier plan draft referenced ``search/rss.cfm?JobCat={id}`` — the LIVE
directory at higheredjobs.com/rss/ uses ``rss/categoryFeed.cfm?catID={id}``;
verified 2026-07-01 by fetching the directory once and capturing catID=148.)

Each ``<item>`` carries:
    <title>       the JOB TITLE (e.g. "Manager of Faculty Relations")
    <description> "Company Name (City, State)"  -- company + location, NOT a body
    <link>        the posting detail URL
    <guid>        same as <link>
    <pubDate>     RFC-822 date

So company + location are parsed OUT of <description> (unlike the other feeds
where <description> is a body), using the trailing "(...)" as the location and
the leading text as the company.

CATEGORY MAP (CATEGORIES below) is an honest slice of the live directory captured
2026-07-01 — the education/teaching/faculty/admin categories a non-tech education
seeker cares about. It is intentionally NOT the full ~130-category list: only the
categories that map cleanly to the education/teaching/faculty/admin industries
this client is gated to. Add more by extending CATEGORIES.

INDUSTRY GATING: this client self-skips (fetches nothing) unless the active
project's industry maps to an education-family category set (see
_categories_for_industry). A welder's or nurse's project polls no HigherEd feeds;
an education/teaching/faculty/academic-admin field gets them automatically. That
gate is why it is safe to add to DAILY_SOURCES — it is inert for every non-education
field.
"""
from typing import Optional

from models import JobResult
from scrape.xml_safe import _safe_fromstring
from search.single_feed_client import SingleFeedClient

HIGHEREDJOBS_FEED_URL = "https://www.higheredjobs.com/rss/categoryFeed.cfm?catID={cat_id}"
HIGHEREDJOBS_RATE_LIMIT = 5

# catID -> short category label. Honest subset captured live from the directory
# (higheredjobs.com/rss/) on 2026-07-01, scoped to education/teaching/faculty/
# academic-admin. Each entry is a real, live category id from that page.
CATEGORIES: dict[int, str] = {
    # Faculty / academic
    148: "Faculty Affairs",
    150: "Laboratory and Research",
    217: "Curriculum Design",
    218: "Instructional Technology and Design",
    220: "Online and Distance Education Programs",
    219: "Adult and Continuing Education Programs",
    216: "Tutors and Learning Resources",
    # Executive / leadership (provost, deans, presidents)
    4: "Presidents and Chancellors",
    164: "Administrative Vice Presidents",
    207: "Other Executive",
    # Student-facing / administrative
    1: "Academic Advising",
    14: "Admissions and Enrollment",
    40: "Student Affairs and Services",
    149: "Registrars",
    22: "Career Development and Services",
    31: "Institutional Research and Planning",
    43: "Other Administrative Positions",
}

# Industry tokens (see industry_profile._tokens) that mean "poll HigherEdJobs".
# Any overlap between the project industry's tokens and this set activates the
# client. Kept education-specific so a nursing/trade/eng field never triggers it.
_EDUCATION_TOKENS = frozenset({
    "education", "teacher", "teaching", "faculty", "academic", "academia",
    "professor", "instructor", "lecturer", "tutor", "school", "university",
    "college", "higher", "highered", "curriculum", "provost", "dean", "registrar",
    "scholarly", "pedagogy", "educator",
})


def _categories_for_industry(industry: Optional[str]) -> list[int]:
    """The catIDs to poll for a project's industry, or [] to SELF-SKIP.

    Returns every catID in CATEGORIES when the industry is education-family
    (token overlap with _EDUCATION_TOKENS), else []. An empty/None industry
    (Alex's engineering default) returns [] -> the client is inert, so adding it
    to DAILY_SOURCES changes nothing for a non-education project."""
    import industry_profile
    toks = set(industry_profile._tokens(industry or ""))
    if not toks:
        return []
    if toks & _EDUCATION_TOKENS:
        return list(CATEGORIES.keys())
    return []


def _split_company_location(description: str) -> tuple[str, str]:
    """HigherEdJobs <description> is 'Company Name (City, State)'. Split the
    trailing parenthetical as the location and the leading text as the company.
    A description with no '(...)' yields (whole string, '')."""
    desc = (description or "").strip()
    if not desc:
        return "Unknown", ""
    if desc.endswith(")") and "(" in desc:
        idx = desc.rfind("(")
        company = desc[:idx].strip()
        location = desc[idx + 1:-1].strip()
        return (company or "Unknown"), location
    return desc, ""


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _parse_feed(raw) -> list[dict]:
    """Parse the RSS 2.0 XML into plain dicts (JSON-cacheable). A malformed or
    unparseable document yields an empty list rather than raising."""
    try:
        root = _safe_fromstring(raw)  # XXE/billion-laughs-safe
    except Exception:
        return []
    items = []
    try:
        for item in root.iter("item"):
            items.append({
                "title": _text(item, "title"),
                "link": _text(item, "link"),
                "description": _text(item, "description"),
                "pubDate": _text(item, "pubDate"),
            })
    except Exception:
        return []
    return items


class HigherEdJobsClient(SingleFeedClient):
    cache_subdir = "higheredjobs"
    rate_limit = HIGHEREDJOBS_RATE_LIMIT

    def __init__(self, cache_dir=None, cache_enabled: bool = True,
                 industry: Optional[str] = None):
        super().__init__(cache_dir=cache_dir, cache_enabled=cache_enabled)
        # Resolve the categories to poll ONCE at construction from the active
        # project's industry (explicit arg wins for tests). [] => self-skip.
        if industry is None:
            try:
                from search.source_taxonomy import active_industry
                industry = active_industry()
            except Exception:
                industry = ""
        self.industry = industry or ""
        self.cat_ids = _categories_for_industry(self.industry)

    def _fetch_category(self, cat_id: int) -> list[dict]:
        def fetch():
            self.limiter.acquire()
            url = HIGHEREDJOBS_FEED_URL.format(cat_id=cat_id)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return {"items": _parse_feed(response.content)}

        return self._cached(f"cat_{cat_id}", fetch).get("items", [])

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        # Single document per category; page>1 has nothing more. Self-skip
        # (no category maps to this industry) returns an empty payload -> 0 jobs.
        if page > 1 or not self.cat_ids:
            return {"items": []}
        items: list[dict] = []
        for cat_id in self.cat_ids:
            items.extend(self._fetch_category(cat_id))
        # National feed (rows carry real "City, State"): thread the search
        # location so parse_results can localize to the user's metro or, on a
        # remote-only search, tag rows nationwide so they survive per remote_ok.
        return {"items": items, "_location": location or ""}

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        from search.remote_intent import (
            is_remote_only, metro_variant_set, remote_region_of,
            tag_nationwide_remote)
        search_loc = raw.get("_location", "") or ""
        remote = is_remote_only(search_loc)
        region = remote_region_of(search_loc) if remote else None
        # Localize only when we resolved real variants (unresolvable -> fail open).
        metro_variants = None
        if search_loc and not remote:
            mv = metro_variant_set(search_loc)
            metro_variants = mv or None
        results = []
        for item in raw.get("items", []) or []:
            title = (item.get("title", "") or "").strip()
            if not title:
                continue
            company, location = _split_company_location(item.get("description", ""))
            # Filter on the title (the description carries only company+location,
            # not a body, so it isn't useful match text — match the title).
            if not keyword_matches(source_keyword, title):
                continue
            if remote:
                location = tag_nationwide_remote(location, region)
            elif metro_variants is not None:
                low = (location or "").lower()
                is_remote_row = "remote" in low
                if location and not is_remote_row and not any(
                        v in low for v in metro_variants):
                    continue
            link = item.get("link", "") or ""
            results.append(JobResult(
                title=title,
                company=company,
                location=location,
                salary_min=None,
                salary_max=None,
                description="",
                url=link,
                source_keyword=source_keyword,
                created=item.get("pubDate", "") or "",
                job_id=f"higheredjobs_{link}" if link else "",
                source_api="higheredjobs",
            ))
        return results
