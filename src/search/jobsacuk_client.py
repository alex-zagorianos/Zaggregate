"""jobs.ac.uk per-subject-area RSS — UK academic / research / health jobs.

RETIRED (2026-07): jobs.ac.uk has permanently removed its entire RSS
infrastructure upstream. Verified July 2026 — ``/feeds``, ``/feeds/subject-
areas``, and every ``/feeds/subject-areas/<slug>`` path (including all guesses
in SUBJECT_AREAS below) return real 404s, and the live site exposes NO feed
links anywhere in its markup; no query-param or path variant returns XML. This
supersedes the earlier (2026-07-01) PROVISIONAL finding, which had assumed a
slug-naming bug — it is not a slug bug, it is a permanent upstream retirement
of the feed product. The client is disabled at the ``RETIRED`` flag below
rather than deleted, so a future session can revive it cheaply (flip the flag)
if jobs.ac.uk ever ships feeds again — UK coverage in the meantime continues
via Adzuna's ``gb`` country routing (search/adzuna_client.py).

``search()`` short-circuits on ``RETIRED`` before any network call or opt-in
check, so this source never polls and never raises the recurring 404s a live
poll would produce. The historical opt-in machinery (``opt_in_active`` /
``self.active`` — "activate on a truthy config flag or a non-US project
country") is left in place for the same revival-cheapness reason, but no
longer controls whether a fetch happens.

Standard RSS item tags assumed (kept for a future revival):
    <title> <link> <description> <pubDate> <guid>
"""
from typing import Optional

from models import JobResult
from scrape.xml_safe import _safe_fromstring
from search.single_feed_client import SingleFeedClient

# Flip to False (and re-verify the feed URL/slugs live) to revive this source.
RETIRED = True
RETIRED_NOTE = (
    "jobs.ac.uk retired its RSS feeds upstream (2026) — source disabled; "
    "UK coverage continues via Adzuna gb"
)

JOBSACUK_FEED_URL = "https://www.jobs.ac.uk/feeds/subject-areas/{area}"
JOBSACUK_RATE_LIMIT = 5

# Subject-area slug -> label, kept for a future revival (see RETIRED above) —
# derived from jobs.ac.uk's published subject-area names. UK academic/health.
# CONFIRMED 404 (2026-07): every one of these paths under
# /feeds/subject-areas/ returns a real 404, not a slug-naming issue.
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
    """RAISES on a malformed/unparseable document instead of swallowing to []
    -- see search.higheredjobs_client._parse_feed's docstring: a parse failure
    must propagate so SingleFeedClient._cached() skips the cache write (S35
    finding #5), rather than caching a false "empty feed" for the full TTL."""
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
        # RETIRED short-circuit FIRST: upstream deleted the feeds entirely, so
        # this must never poll — regardless of self.active/opt-in state — and
        # never raise a 404. See module docstring / RETIRED_NOTE.
        if RETIRED:
            return {"items": []}
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
