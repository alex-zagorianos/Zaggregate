"""jobs.ac.uk per-subject-area RSS — UK academic / research / health jobs.

PROVISIONAL (endpoint unverified): the plan's documented feed pattern is

    https://www.jobs.ac.uk/feeds/subject-areas/{area}

but on 2026-07-01 every automated probe of that path (and several slug guesses)
returned 404/HTML, and jobs.ac.uk exposes no feed links to an unauthenticated
fetch — so the exact live slug scheme could NOT be confirmed against a real feed.
The parser below assumes a standard RSS 2.0 document (the shape jobs.ac.uk has
historically served). Treat the SUBJECT_AREAS slugs and the URL template as
UNVERIFIED until checked against a live response. See deviations.

OPT-IN ONLY. This client is deliberately excluded from a default US run and from
DAILY_SOURCES. It activates only when the project EXPLICITLY opts in — either a
truthy config flag ``jobsacuk`` / ``sources.jobsacuk``, or a non-US project
country (config.adzuna_country_for on the project's location/country resolves to
something other than 'us', e.g. a UK-based seeker). A default Cincinnati run never
polls it. This matches the plan: "never in a default US run".

Standard RSS item tags assumed:
    <title> <link> <description> <pubDate> <guid>
"""
from typing import Optional

from models import JobResult
from scrape.xml_safe import _safe_fromstring
from search.single_feed_client import SingleFeedClient

JOBSACUK_FEED_URL = "https://www.jobs.ac.uk/feeds/subject-areas/{area}"
JOBSACUK_RATE_LIMIT = 5

# Subject-area slug -> label. UNVERIFIED against a live feed (see module docstring)
# — derived from jobs.ac.uk's published subject-area names. UK academic/health.
SUBJECT_AREAS: dict[str, str] = {
    "nursing-and-midwifery-jobs": "Nursing and Midwifery",
    "health-and-medical-jobs": "Health and Medical",
    "biological-sciences-jobs": "Biological Sciences",
}

# Industry tokens that select which subject-area feeds to poll (only used once the
# client is already opted in). Empty overlap -> poll all mapped areas.
_AREA_TOKENS: dict[str, frozenset] = {
    "nursing-and-midwifery-jobs": frozenset({"nursing", "nurse", "midwife", "midwifery"}),
    "health-and-medical-jobs": frozenset(
        {"health", "healthcare", "medical", "clinical", "hospital", "patient"}),
    "biological-sciences-jobs": frozenset(
        {"biology", "biological", "biomedical", "life", "sciences", "research"}),
}


def opt_in_active(industry: Optional[str], cfg: Optional[dict] = None) -> bool:
    """True only when the project has EXPLICITLY opted in to UK academic feeds.

    Two triggers (either suffices):
      * a truthy config flag ``jobsacuk`` (or ``sources.jobsacuk``), or
      * a non-US project country (adzuna_country_for on the config's
        location/country resolves to != 'us').
    Default (US project, no flag) -> False -> the client is inert. This is the
    guard that keeps jobs.ac.uk out of a default US run."""
    cfg = cfg or {}
    if cfg.get("jobsacuk"):
        return True
    src = cfg.get("sources") or {}
    if isinstance(src, dict) and src.get("jobsacuk"):
        return True
    try:
        import config
        country = config.adzuna_country_for(
            location=cfg.get("location"), country=cfg.get("country")
            or cfg.get("adzuna_country"))
        if (country or "us").strip().lower() != "us":
            return True
    except Exception:
        pass
    return False


def _areas_for_industry(industry: Optional[str]) -> list[str]:
    """Subject-area slugs to poll for this field. A field whose tokens match a
    specific area polls only that area; no match -> poll all mapped areas (broad
    UK academic net)."""
    import industry_profile
    toks = set(industry_profile._tokens(industry or ""))
    matched = [slug for slug, sig in _AREA_TOKENS.items() if toks & sig]
    return matched or list(SUBJECT_AREAS.keys())


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _parse_feed(raw) -> list[dict]:
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


class JobsAcUkClient(SingleFeedClient):
    cache_subdir = "jobsacuk"
    rate_limit = JOBSACUK_RATE_LIMIT

    def __init__(self, cache_dir=None, cache_enabled: bool = True,
                 industry: Optional[str] = None, cfg: Optional[dict] = None,
                 opt_in: Optional[bool] = None):
        super().__init__(cache_dir=cache_dir, cache_enabled=cache_enabled)
        if industry is None:
            try:
                from search.source_taxonomy import active_industry
                industry = active_industry()
            except Exception:
                industry = ""
        self.industry = industry or ""
        # Opt-in state: explicit arg wins (tests); else derive from cfg.
        self.active = opt_in if opt_in is not None else opt_in_active(self.industry, cfg)
        self.areas = _areas_for_industry(self.industry) if self.active else []

    def _fetch_area(self, area: str) -> list[dict]:
        def fetch():
            self.limiter.acquire()
            url = JOBSACUK_FEED_URL.format(area=area)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return {"items": _parse_feed(response.content)}

        return self._cached(f"area_{area}", fetch).get("items", [])

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        if page > 1 or not self.active or not self.areas:
            return {"items": []}
        items: list[dict] = []
        for area in self.areas:
            items.extend(self._fetch_area(area))
        return {"items": items}

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("items", []) or []:
            title = (item.get("title", "") or "").strip()
            if not title:
                continue
            desc = self.strip_html(item.get("description", "") or "")
            if not keyword_matches(source_keyword, f"{title} {desc}"):
                continue
            link = item.get("link", "") or ""
            results.append(JobResult(
                title=title,
                company="Unknown",  # jobs.ac.uk RSS carries the employer in the body
                location="United Kingdom",
                salary_min=None,
                salary_max=None,
                description=desc[:3000],
                url=link,
                source_keyword=source_keyword,
                created=item.get("pubDate", "") or "",
                job_id=f"jobsacuk_{link}" if link else "",
                source_api="jobsacuk",
            ))
        return results
