"""RNJobSite per-specialty RSS — free, no key, sanctioned public feeds.

RNJobSite publishes RSS 2.0 feeds of registered-nurse postings. Two feed shapes,
both verified live 2026-07-01 (directory at rnjobsite.com/rss/links):

    base feed:      https://www.rnjobsite.com/rss/jobs
    per-specialty:  https://www.rnjobsite.com/rss/jobs/type/{type_id}

Each ``<item>`` carries custom, non-standard child tags (captured live):
    <title>              CDATA job title
    <link> / <guid>      posting URL
    <hiringOrganization> CDATA employer name
    <jobLocation>        CDATA "City ST"
    <pubDate>            RFC-822 date
    <description>        CDATA body

The specialty ``type_id`` map (SPECIALTIES) is an honest subset: the directory
only surfaces a specialty feed when it currently has live jobs, so only the
type_ids observed live on 2026-07-01 are hard-coded. The stable base feed
(``/rss/jobs``, "most recent RN jobs") is ALWAYS included so the source has
coverage even when no captured specialty feed happens to be live. Add more
type_ids as they are observed.

INDUSTRY GATING: self-skips unless the active project's industry is a nursing /
healthcare-clinical field (see _should_poll). An eng/finance/trade project polls
no RN feeds; a nursing/RN/healthcare field gets them automatically. That gate is
why it is safe in DAILY_SOURCES.
"""
from typing import Optional

from models import JobResult
from scrape.xml_safe import _safe_fromstring
from search.single_feed_client import SingleFeedClient

RNJOBSITE_BASE_URL = "https://www.rnjobsite.com/rss/jobs"
RNJOBSITE_TYPE_URL = "https://www.rnjobsite.com/rss/jobs/type/{type_id}"
RNJOBSITE_RATE_LIMIT = 5

# type_id -> specialty label. Honest subset: only feeds observed live in the
# directory on 2026-07-01 (a specialty feed appears only when it has live jobs).
SPECIALTIES: dict[int, str] = {
    444: "Correctional / Correctional Health",
    452: "Hospice",
    573: "Labor & Delivery",
}

# Industry tokens that mean "poll RNJobSite". Any overlap activates it. Kept
# nursing/clinical-specific so an eng/finance/trade field never triggers it.
_NURSING_TOKENS = frozenset({
    "nursing", "nurse", "rn", "lpn", "lvn", "cna", "caregiver", "clinical",
    "healthcare", "health", "hospital", "patient", "bedside", "medical",
    "hospice", "midwife", "midwifery",
})


def _should_poll(industry: Optional[str]) -> bool:
    """True when the project's industry is a nursing/healthcare-clinical field.
    Empty/None (Alex's engineering default) -> False -> the client is inert, so
    adding it to DAILY_SOURCES changes nothing for a non-nursing project."""
    import industry_profile
    toks = set(industry_profile._tokens(industry or ""))
    return bool(toks & _NURSING_TOKENS)


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _parse_feed(raw) -> list[dict]:
    """Parse the RSS 2.0 XML into plain dicts (JSON-cacheable). Reads RNJobSite's
    custom <hiringOrganization>/<jobLocation> tags. Malformed/unparseable ->
    empty list rather than raising."""
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
                "company": _text(item, "hiringOrganization"),
                "location": _text(item, "jobLocation"),
                "description": _text(item, "description"),
                "pubDate": _text(item, "pubDate"),
            })
    except Exception:
        return []
    return items


class RNJobSiteClient(SingleFeedClient):
    cache_subdir = "rnjobsite"
    rate_limit = RNJOBSITE_RATE_LIMIT

    def __init__(self, cache_dir=None, cache_enabled: bool = True,
                 industry: Optional[str] = None):
        super().__init__(cache_dir=cache_dir, cache_enabled=cache_enabled)
        if industry is None:
            try:
                from search.source_taxonomy import active_industry
                industry = active_industry()
            except Exception:
                industry = ""
        self.industry = industry or ""
        self.active = _should_poll(self.industry)

    def _feed_urls(self) -> list[tuple[str, str]]:
        """(cache_key, url) pairs to fetch: the stable base feed plus every
        captured specialty feed."""
        urls = [("base", RNJOBSITE_BASE_URL)]
        for type_id in SPECIALTIES:
            urls.append((f"type_{type_id}", RNJOBSITE_TYPE_URL.format(type_id=type_id)))
        return urls

    def _fetch(self, key: str, url: str) -> list[dict]:
        def fetch():
            self.limiter.acquire()
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return {"items": _parse_feed(response.content)}

        return self._cached(key, fetch).get("items", [])

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        if page > 1 or not self.active:
            return {"items": []}
        # Same posting can appear in the base feed AND a specialty feed; dedup by
        # link here so a job isn't double-counted before it reaches the engine.
        seen: set[str] = set()
        items: list[dict] = []
        for key, url in self._feed_urls():
            for it in self._fetch(key, url):
                link = it.get("link", "") or ""
                if link and link in seen:
                    continue
                if link:
                    seen.add(link)
                items.append(it)
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
                company=(item.get("company", "") or "Unknown").strip() or "Unknown",
                location=(item.get("location", "") or "").strip(),
                salary_min=None,
                salary_max=None,
                description=desc[:3000],
                url=link,
                source_keyword=source_keyword,
                created=item.get("pubDate", "") or "",
                job_id=f"rnjobsite_{link}" if link else "",
                source_api="rnjobsite",
            ))
        return results
