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
    custom <hiringOrganization>/<jobLocation> tags.

    RAISES on a malformed/unparseable document instead of swallowing to [] --
    see search.higheredjobs_client._parse_feed's docstring for why: a parse
    failure must propagate so SingleFeedClient._cached() skips the cache write
    (S35 finding #5), rather than caching a false "empty feed" for the full TTL."""
    root = _safe_fromstring(raw)  # XXE/billion-laughs-safe; raises on bad XML
    items = []
    for item in root.iter("item"):
        items.append({
            "title": _text(item, "title"),
            "link": _text(item, "link"),
            "company": _text(item, "hiringOrganization"),
            "location": _text(item, "jobLocation"),
            "description": _text(item, "description"),
            "pubDate": _text(item, "pubDate"),
        })
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
        # This is a NATIONAL feed (no location filter); its rows carry real cities
        # that otherwise die at the metro location gate (244 -> 0 for a metro-bound
        # nurse). Thread the search location so parse_results can localize to the
        # user's metro (real locality) or, on a remote-only search, tag rows as
        # nationwide so they survive per remote_ok. Empty location = no gating.
        return {"items": items, "_location": location or ""}

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        from search.remote_intent import (
            is_remote_only, metro_state_set, metro_variant_set,
            national_row_locality, remote_region_of, tag_nationwide_remote)
        location = raw.get("_location", "") or ""
        remote = is_remote_only(location)
        region = remote_region_of(location) if remote else None
        # Localize only when we resolved real metro variants — an unresolvable
        # location must NOT drop every row (fail open, like the downstream gate).
        metro_variants = None
        metro_states: set[str] = set()
        if location and not remote:
            mv = metro_variant_set(location)
            metro_variants = mv or None
            metro_states = metro_state_set(location)
        # Metro-bound: collect true-metro rows and same-state (commutable) rows
        # separately, then fail open to same-state if the strict metro filter would
        # empty the feed — mirroring reap/edjoin. A same-name out-of-state city
        # ("Columbus, GA" for a "Columbus, OH" seeker) is rejected by the state gate.
        metro_rows: list[JobResult] = []
        state_rows: list[JobResult] = []
        for item in raw.get("items", []) or []:
            title = (item.get("title", "") or "").strip()
            if not title:
                continue
            desc = self.strip_html(item.get("description", "") or "")
            if not keyword_matches(source_keyword, f"{title} {desc}"):
                continue
            row_loc = (item.get("location", "") or "").strip()
            bucket = "metro"
            if remote:
                # Genuinely-nationwide search: keep the row, mark it remote/US so
                # the location gate keeps it per remote_ok (origin city preserved).
                row_loc = tag_nationwide_remote(row_loc, region)
            elif metro_variants is not None:
                bucket = national_row_locality(row_loc, metro_variants, metro_states)
                if bucket == "other":
                    continue                  # out-of-area / wrong-state same-name city
            link = item.get("link", "") or ""
            job = JobResult(
                title=title,
                company=(item.get("company", "") or "Unknown").strip() or "Unknown",
                location=row_loc,
                salary_min=None,
                salary_max=None,
                description=desc[:3000],
                url=link,
                source_keyword=source_keyword,
                created=item.get("pubDate", "") or "",
                job_id=f"rnjobsite_{link}" if link else "",
                source_api="rnjobsite",
            )
            if bucket == "state":
                state_rows.append(job)
            else:                             # 'metro' or 'remote'
                metro_rows.append(job)
        # Keep true-metro rows AND in-state (CBSA member-state) rows — metro_variants
        # only holds the CBSA principal city, so genuine in-metro SUBURBS (Edgewood
        # KY / Hamilton OH for a Cincinnati seeker) land in the state bucket and must
        # survive to scoring (where _location_score ranks true-metro higher) rather
        # than be dropped. Only 'other' (out-of-state, incl. a same-name city like
        # Columbus GA for a Columbus OH seeker) was already filtered. Metro rows lead.
        return metro_rows + state_rows
